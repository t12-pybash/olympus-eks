# olympus-eks

Production-pattern GPU inference on AWS EKS. Part of the [Olympus platform](https://t-12.io).

Provisions the infrastructure for running vLLM on GPU nodes, managed by Karpenter for on-demand spot provisioning and scale-to-zero. LiteLLM sits in front as an OpenAI-compatible router.

---

## Stack

| Layer | Technology |
|---|---|
| Cloud | AWS EKS |
| IaC | Terraform ~1.6, modular VPC / EKS / Karpenter |
| GPU Autoscaling | Karpenter: g4dn.xlarge/2xlarge spot, scale-to-zero |
| Inference | vLLM (OpenAI-compatible API) |
| Router | LiteLLM |
| CI | GitLab CI: validate → plan → apply (manual gate) |
| State | S3 + DynamoDB lock |

---

## Architecture

                ┌─────────────────────────────────┐
                │         AWS EKS Cluster          │
                │                                  │
  Request ─────────▶│  LiteLLM (system node)           │
                    │       │                          │
                    │       ▼                          │
                    │  vLLM (Karpenter GPU node)        │
                    │  g4dn.xlarge · T4 16GB · spot    │
                    │                                  │
                    └─────────────────────────────────┘
                              ▲
                    Karpenter provisions node
                    when pod is pending,
                    terminates when idle 30s

## Repository Structure

olympus-eks/
├── terraform/
│   ├── modules/
│   │   ├── vpc/        VPC, public/private subnets, NAT gateway
│   │   ├── eks/        EKS cluster, OIDC provider, system node group
│   │   └── karpenter/  Karpenter IAM, Helm install
│   ├── main.tf
│   ├── variables.tf
│   ├── outputs.tf
│   └── versions.tf
└── kubernetes/
    ├── karpenter/      NodePool and EC2NodeClass for GPU nodes
    ├── nvidia/         NVIDIA device plugin DaemonSet
    ├── vllm/           vLLM Deployment and Service
    └── litellm/        LiteLLM Deployment, Service, ConfigMap

---

## Prerequisites

- AWS account with IAM permissions for EKS, EC2, VPC
- Terraform >= 1.6
- S3 bucket `olympus-eks-tfstate` and DynamoDB table `olympus-eks-tflock` for state backend
- HuggingFace token (for model download) in a Kubernetes secret

## Deploy

```bash
# Bootstrap state backend (one-time)
aws s3 mb s3://olympus-eks-tfstate --region eu-west-1
aws dynamodb create-table \
  --table-name olympus-eks-tflock \
  --attribute-definitions AttributeName=LockID,AttributeType=S \
  --key-schema AttributeName=LockID,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST \
  --region eu-west-1

# Deploy infrastructure
cd terraform
terraform init
terraform plan
terraform apply

# Configure kubectl
aws eks update-kubeconfig --region eu-west-1 --name olympus-eks

# Apply Kubernetes manifests
kubectl apply -f kubernetes/vllm/namespace.yaml
kubectl apply -f kubernetes/nvidia/
kubectl apply -f kubernetes/karpenter/
kubectl apply -f kubernetes/vllm/
kubectl apply -f kubernetes/litellm/

---

Cost

┌─────────────────────────────┬────────────────────────────────────┐
│           Config            │                Cost                │
├─────────────────────────────┼────────────────────────────────────┤
│ g4dn.xlarge spot            │ ~€0.15/hr                          │
├─────────────────────────────┼────────────────────────────────────┤
│ g4dn.xlarge on-demand       │ ~€0.49/hr                          │
├─────────────────────────────┼────────────────────────────────────┤
│ System nodes (t3.medium x2) │ ~€0.09/hr                          │
├─────────────────────────────┼────────────────────────────────────┤
│ Karpenter scale-to-zero     │ GPU nodes only exist while serving │
└─────────────────────────────┴────────────────────────────────────┘

---

## Deployment Notes

Real-world gotchas from the initial deploy, documented so the second run is clean.

### AWS account setup (new accounts)

- **Upgrade to paid plan** before applying. The free plan blocks t3.medium and all G instances
- **Request GPU quotas in the correct region** (eu-west-1) before running `terraform apply`:
  - Service Quotas → EC2 → *Running On-Demand G and VT instances* → request 4 vCPUs
  - Service Quotas → EC2 → *All G and VT Spot Instance Requests* → request 4 vCPUs
  - New accounts are denied by default; appeal with a use case description. Approved same day
- **Create EC2 Spot service-linked role**: new accounts don't have it:
  ```bash
  aws iam create-service-linked-role --aws-service-name spot.amazonaws.com
  ```

### Security group tag (required for Karpenter)

Terraform does not tag the EKS cluster security group with `karpenter.sh/discovery`. Do it manually after `terraform apply`:

```bash
SG_ID=$(aws eks describe-cluster --name olympus-eks --region eu-west-1 \
  --query 'cluster.resourcesVpcConfig.clusterSecurityGroupId' --output text)
aws ec2 create-tags \
  --resources $SG_ID \
  --tags Key=karpenter.sh/discovery,Value=olympus-eks \
  --region eu-west-1
```

Without this tag, the EC2NodeClass stays `SecurityGroupsReady=False` and Karpenter never provisions GPU nodes.

### Secrets (create before applying manifests)

```bash
kubectl create secret generic vllm-secrets \
  --namespace olympus \
  --from-literal=hf-token=YOUR_HF_TOKEN

kubectl create secret generic litellm-secrets \
  --namespace olympus \
  --from-literal=master-key=sk-olympus-$(openssl rand -hex 16)
```

HuggingFace token requires access to `mistralai/Mistral-7B-Instruct-v0.3`. Accept the model license at huggingface.co first.

### Karpenter Helm timeout

Terraform's Helm provider times out at 5 minutes; Karpenter pods take longer to pass readiness on first install. The timeout error is a false alarm. Check pod status directly:

```bash
kubectl get pods -n karpenter
```

If both pods are `1/1 Running`, Karpenter is healthy. Re-run `terraform apply` to clear the state error.

### Correct manifest apply order

```bash
kubectl apply -f kubernetes/vllm/namespace.yaml   # namespace first
kubectl apply -f kubernetes/karpenter/             # NodePool + EC2NodeClass
kubectl apply -f kubernetes/nvidia/                # device plugin DaemonSet
kubectl apply -f kubernetes/vllm/                  # vLLM deployment
kubectl apply -f kubernetes/litellm/               # LiteLLM deployment
```

### Terraform state: use remote backend from day one

In the first deployment of this cluster, Terraform state was stored locally (`terraform.tfstate` on disk). The state files were lost before teardown. Running `terraform destroy` returned "No changes. Resources: 0 destroyed." With an empty state, Terraform believes nothing exists.

Manual teardown required deleting every resource individually through the AWS CLI:

```bash
# Order matters: dependencies must be deleted bottom-up
kubectl delete nodeclaims --all
aws eks delete-nodegroup --cluster-name olympus-eks --nodegroup-name olympus-eks-system --region eu-west-1
aws eks wait nodegroup-deleted --cluster-name olympus-eks --nodegroup-name olympus-eks-system --region eu-west-1
aws ec2 delete-nat-gateway --nat-gateway-id <nat-id> --region eu-west-1
aws eks delete-cluster --name olympus-eks --region eu-west-1
aws eks wait cluster-deleted --name olympus-eks --region eu-west-1
# Then subnets, route tables, IGW, EIP, VPC in that order
```

This took 20 minutes and required looking up each resource ID from the AWS console.

**Mitigation:** Bootstrap the S3 backend before running `terraform init`. The `Deploy` section above includes this as the first step. Never skip it. Losing state means losing the ability to use Terraform for teardown.

## Related

- Argus: autonomous SRE agent for the Olympus platform
- t-12.io: write-ups on the full stack
  EOF
