variable "aws_region" {
  description = "AWS region to deploy into"
  type        = string
  default     = "eu-west-1"
}

variable "cluster_name" {
  description = "EKS cluster name"
  type        = string
  default     = "olympus-eks"
}

variable "vpc_cidr" {
  description = "VPC CIDR block"
  type        = string
  default     = "10.0.0.0/16"
}

variable "kubernetes_version" {
  description = "EKS Kubernetes version"
  type        = string
  default     = "1.31"
}

variable "gpu_instance_types" {
  description = "GPU instance types for Karpenter NodePool"
  type        = list(string)
  default     = ["g4dn.xlarge", "g4dn.2xlarge"]
}
