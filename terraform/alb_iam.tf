# 1. IAM Policy 리소스 생성
# (curl로 다운로드한 iam_policy.json 파일을 직접 참조)
resource "aws_iam_policy" "alb_controller_policy" {
  name_prefix = "EKS-ALB-Controller-Policy-"
  policy      = file("iam_policy.json")
}

# 2. EKS 클러스터가 컨트롤러(Pod)를 인증할 수 있도록 신뢰 관계 설정
#    (IRSA - IAM Roles for Service Accounts)
data "aws_iam_policy_document" "alb_assume_role_policy" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]
    
    principals {
      type        = "Federated"
      # [하드코딩 1] AWS 콘솔에서 확인한 실제 OIDC ARN
      identifiers = ["arn:aws:iam::798874239435:oidc-provider/oidc.eks.ap-northeast-2.amazonaws.com/id/C1DAF7C4C472B1AEE2D33CD26C9E13AB"]
    }
    
    # [최종 수정]
    # 'sts.amazonaws.com'을 대상으로 하는 토큰만 신뢰하도록
    # ':aud' 조건을 StringEquals에 추가합니다.
    condition {
      test     = "StringEquals"
      variable = "oidc.eks.ap-northeast-2.amazonaws.com/id/C1DAF7C4C472B1AEE2D33CD26C9E13AB:sub"
      values   = ["system:serviceaccount:kube-system:aws-load-balancer-controller"]
    }
    # [이 부분이 추가되었습니다]
    condition {
      test     = "StringEquals"
      variable = "oidc.eks.ap-northeast-2.amazonaws.com/id/C1DAF7C4C472B1AEE2D33CD26C9E13AB:aud"
      values   = ["sts.amazonaws.com"]
    }
  }
}

# 3. 위 신뢰 정책(2)을 기반으로 실제 IAM Role 생성
resource "aws_iam_role" "alb_controller_role" {
  name_prefix        = "EKS-ALB-Controller-Role-"
  assume_role_policy = data.aws_iam_policy_document.alb_assume_role_policy.json
}

# 4. 생성한 Role(3)에 생성한 Policy(1)를 부착
resource "aws_iam_role_policy_attachment" "alb_controller_attach" {
  role       = aws_iam_role.alb_controller_role.name
  policy_arn = aws_iam_policy.alb_controller_policy.arn
}