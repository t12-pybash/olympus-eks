variable "cluster_name" {
  description = "EKS cluster name"
  type        = string
}

variable "cluster_endpoint" {
  description = "EKS cluster API endpoint"
  type        = string
}

variable "oidc_provider_arn" {
  description = "OIDC provider ARN for IRSA"
  type        = string
}

variable "oidc_provider_url" {
  description = "OIDC provider URL for IRSA"
  type        = string
}

variable "node_role_arn" {
  description = "IAM role ARN for Karpenter-provisioned nodes"
  type        = string
}

variable "private_subnet_ids" {
  description = "Private su
  type        = list(string)
}

variable "gpu_instance_type
  description = "GPU instance types for the NodePool"
  type        = list(string
  default     = ["g4dn.xlarge", "g4dn.2xlarge"]
}
