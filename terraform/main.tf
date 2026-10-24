module "vpc" {
  source = "./modules/vpc"

  name = var.cluster_name
  cidr = var.vpc_cidr
}

module "eks" {
  source = "./modules/eks"

  name               = var.cluster_name
  kubernetes_version = var.kubernetes_version
  public_subnet_ids  = module.vpc.public_subnet_ids
  private_subnet_ids = module.vpc.private_subnet_ids
}

module "karpenter" {
  source = "./modules/karpenter"

  cluster_name       = module.eks.cluster_name
  cluster_endpoint   = module.eks.cluster_endpoint
  oidc_provider_arn  = module.eks.oidc_provider_arn
  oidc_provider_url  = module.eks.oidc_provider_url
  node_role_arn      = module.eks.node_role_arn
  private_subnet_ids = module.vpc.private_subnet_ids
  gpu_instance_types = var.gpu_instance_types
}
