# EKS는 복잡한 네트워크(VPC) 설정이 필요합니다.
# 공식 VPC 모듈을 사용하면 이 과정을 자동화할 수 있습니다.
module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "5.5.3"

  name = "${var.cluster_name}-vpc"
  cidr = var.vpc_cidr

  azs = ["${var.aws_region}a", "${var.aws_region}b"] # 2개의 가용 영역 사용

  # EKS에 필요한 Public/Private 서브넷을 생성합니다.
  public_subnets  = [for k, v in module.vpc.azs : cidrsubnet(var.vpc_cidr, 8, k)]
  private_subnets = [for k, v in module.vpc.azs : cidrsubnet(var.vpc_cidr, 8, k + length(module.vpc.azs))]

  enable_nat_gateway   = true # Private 서브넷이 인터넷에 접속할 수 있도록 (예: ECR 이미지 PULL)
  single_nat_gateway   = true # 비용 절감을 위해 NAT 게이트웨이 1개만 사용
  enable_dns_hostnames = true

  # [중요]
  # Ingress 컨트롤러(ALB)와 EKS가 서브넷을 찾을 수 있도록 태그를 지정합니다.
  public_subnet_tags = {
    "kubernetes.io/cluster/${var.cluster_name}" = "shared"
    "kubernetes.io/role/elb"                  = "1"
  }
  private_subnet_tags = {
    "kubernetes.io/cluster/${var.cluster_name}" = "shared"
    "kubernetes.io/role/internal-elb"         = "1"
  }
}