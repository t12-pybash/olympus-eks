# IAM role for Karpenter controller (IRSA)
resource "aws_iam_role" "karpenter" {
  name = "${var.cluster_name}-karpenter"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRoleWithWebIdentity"
      Effect = "Allow"
      Principal = {
        Federated = var.oidc_provider_arn
      }
      Condition = {
        StringEquals = {
          "${var.oidc_provider_url}:sub" = "system:serviceaccount:karpenter:karpenter"
          "${var.oidc_provider_url}:aud" = "sts.amazonaws.com"
        }
      }
    }]
  })
}

resource "aws_iam_role_policy" "karpenter" {
  name = "${var.cluster_nam
  role = aws_iam_role.karpenter.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "ec2:CreateLaunchTemplate",
          "ec2:CreateFleet"
          "ec2:RunInstances",
          "ec2:CreateTags",
          "ec2:TerminateInstances",
          "ec2:DescribeLaun
          "ec2:DescribeInstances",
          "ec2:DescribeSecu
          "ec2:DescribeSubnets",
          "ec2:DescribeInst
          "ec2:DescribeInstanceTypeOfferings",
          "ec2:DescribeAvai
          "ec2:DescribeSpotPriceHistory",
          "pricing:GetProdu
          "ssm:GetParameter",
        ]
        Resource = "*"
      },
      {
        Effect   = "Allow"
        Action   = ["iam:PassRole"]
        Resource = var.node
      }
    ]
  })
}

# Karpenter installed via H
resource "helm_release" "karpenter" {
  name             = "karpe
  namespace        = "karpenter"
  create_namespace = true
  repository       = "oci://public.ecr.aws/karpenter"
  chart            = "karpe
  version          = "1.0.0"

  set {
    name  = "settings.clust
    value = var.cluster_name
  }

  set {
    name  = "settings.clusterEndpoint"
    value = var.cluster_end
  }

  set {
    name  = "serviceAccount\.com/role-arn"
    value = aws_iam_role.karpenter.arn
  }
}
