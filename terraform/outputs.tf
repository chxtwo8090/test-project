output "cluster_name" {
  description = "EKS 클러스터 이름"
  value       = module.eks.cluster_name
}

output "cluster_endpoint" {
  description = "EKS 클러스터 API 서버 주소"
  value       = module.eks.cluster_endpoint
}

output "ecr_repository_url" {
  description = "Flask 앱 이미지를 푸시할 ECR 주소"
  value       = aws_ecr_repository.flask_app.repository_url
}