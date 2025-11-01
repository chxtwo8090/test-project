terraform {
  required_version = ">= 1.3" # Terraform 버전 1.3 이상 권장

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0" # AWS 프로바이더 버전 5.x 권장
    }
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 2.20"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

# --------------------------------------------------
# [추가]
# EKS 클러스터가 생성된 *후에*
# 그 클러스터 정보를 이용해 Kubernetes 프로바이더를 설정합니다.
# --------------------------------------------------
provider "kubernetes" {
  # 1. 클러스터 주소 (EKS 모듈의 output을 참조)
  host                   = module.eks.cluster_endpoint
  # 2. 클러스터 인증서 (EKS 모듈의 output을 참조)
  cluster_ca_certificate = base64decode(module.eks.cluster_certificate_authority_data)

  # 3. 클러스터 인증 토큰 (AWS CLI를 통해 동적으로 받아옴)
  exec {
    api_version = "client.authentication.k8s.io/v1beta1"
    command     = "aws"
    args = [
      "eks",
      "get-token",
      "--cluster-name",
      module.eks.cluster_name,
      "--region",
      var.aws_region
    ]
  }
}