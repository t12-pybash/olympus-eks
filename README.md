# olympus-eks

Production-pattern GPU inference on AWS EKS — part of the [Olympus platform](https://t-12.io).

Provisions the infrastructure for running vLLM on GPU nodes, managed by Karpenter for on-demand spot provisioning and scale-to-zero. LiteLLM sits in front as an OpenAI-compatible router.

---

## Stack

| Layer | Technology |
|---|---|
| Cloud | AWS EKS |
| IaC | Terraform ~1.6, modular VPC / EKS / Karpenter |
| GPU Autoscaling | Karpenter — g4dn.xlarge/2xlarge spot, scale-to-zero |
| Inference | vLLM (OpenAI-compatible API) |
| Router | LiteLLM |
| CI | GitLab CI — validate → plan → apply (manual gate) |
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

Related

- Argus — autonomous SRE agent for the Olympus platform
- t-12.io — write-ups on the full stack
  EOF
