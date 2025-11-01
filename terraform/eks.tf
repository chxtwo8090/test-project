module "eks" {
  source  = "terraform-aws-modules/eks/aws"
  version = "19.0" # EKS 모듈 최신 버전 권장

  cluster_name    = var.cluster_name
  cluster_version = "1.34" # EKS 버전 (원하는 버전으로)

  vpc_id     = module.vpc.vpc_id
  subnet_ids = module.vpc.private_subnets

  # --------------------------------------------------
  # [추가] EKS API 엔드포인트 접근 설정
  # 로컬 PC(외부)에서 EKS API에 접근할 수 있도록 Public 엔드포인트를 '활성화'하고
  # VPC 내부에서만 접근하는 Private 엔드포인트를 '비활성화'합니다.
  cluster_endpoint_public_access  = true
  cluster_endpoint_private_access = false
  # --------------------------------------------------

  # [핵심 - kubectl 인증 문제 해결]
  # 1. Terraform이 aws-auth ConfigMap을 직접 관리하도록 설정
  manage_aws_auth_configmap = true

  # 2. 'data.tf'에서 가져온 '현재 사용자'의 ARN을 EKS 관리자(system:masters)로 등록
aws_auth_users = [
    {
      userarn  = data.aws_caller_identity.current.arn
      username = data.aws_caller_identity.current.user_id # user_id가 맞습니다.
      groups   = ["system:masters"]
    }
  ]
  # 워커 노드(EC2) 그룹 설정
  eks_managed_node_groups = {
    main_nodes = {
      name           = "${var.cluster_name}-group"
      subnet_ids     = module.vpc.private_subnets

      # [중요] 인스턴스 타입: 최소 t3.medium 권장
      instance_types = ["t3.small"]
      capacity_type  = "ON_DEMAND"
      
      min_size     = 1 
      max_size     = 2 
      desired_size = 1 
    }
  }
}