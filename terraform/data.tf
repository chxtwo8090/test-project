# [핵심]
# terraform apply를 실행하는 '현재 IAM 사용자' 정보를 가져옵니다.
# 이 사용자를 EKS 관리자로 등록하여 kubectl 인증 문제를 해결합니다.
data "aws_caller_identity" "current" {}