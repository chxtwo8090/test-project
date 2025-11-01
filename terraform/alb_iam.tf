# 1. 컨트롤러가 사용할 IAM 정책(Policy) 다운로드
#    (AWS가 공식적으로 제공하는 정책 JSON 파일을 사용합니다)
data "http" "alb_controller_policy" {
  url = "https://raw.githubusercontent.com/kubernetes-sigs/aws-load-balancer-controller/v2.7.2/docs/install/iam_policy.json"
}

# 2. 다운로드한 JSON으로 IAM Policy 리소스 생성
resource "aws_iam_policy" "alb_controller_policy" {
  name_prefix = "EKS-ALB-Controller-Policy-"
  policy      = data.http.alb_controller_policy.body
}

# 3. EKS 클러스터가 컨트롤러(Pod)를 인증할 수 있도록 신뢰 관계 설정
#    (IRSA - IAM Roles for Service Accounts)
data "aws_iam_policy_document" "alb_assume_role_policy" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]
    
    principals {
      type        = "Federated"
      # EKS 모듈(v19)이 자동으로 생성한 OIDC 공급자 ARN을 참조합니다.
      identifiers = ["arn:aws:iam::798874239435:oidc-provider/oidc.eks.ap-northeast-2.amazonaws.com/id/C1DAF7C4C472B1AEE2D33CD26C9E13AB"]
    }
    
    # [중요]
    # 'kube-system' 네임스페이스의 'aws-load-balancer-controller'라는
    # ServiceAccount만 이 역할을 사용할 수 있도록 제한합니다.
    condition {
      test     = "StringEquals"
      variable = "${replace(module.eks.cluster_oidc_issuer_url, "https://", "")}:sub"
      values   = ["system:serviceaccount:kube-system:aws-load-balancer-controller"]
    }
  }
}

# 4. 위 신뢰 정책(3)을 기반으로 실제 IAM Role 생성
resource "aws_iam_role" "alb_controller_role" {
  name_prefix        = "EKS-ALB-Controller-Role-"
  assume_role_policy = data.aws_iam_policy_document.alb_assume_role_policy.json
}

# 5. 생성한 Role(4)에 생성한 Policy(2)를 부착
resource "aws_iam_role_policy_attachment" "alb_controller_attach" {
  role       = aws_iam_role.alb_controller_role.name
  policy_arn = aws_iam_policy.alb_controller_policy.arn
}