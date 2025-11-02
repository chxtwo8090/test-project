# 1단계 출력 (VPC, S3)
output "vpc_id" {
  description = "생성된 VPC의 ID"
  value       = aws_vpc.main.id
}

output "public_subnet_ids" {
  description = "생성된 퍼블릭 서브넷 ID 목록 (ALB, ECS 배치용)"
  value       = [aws_subnet.public_a.id, aws_subnet.public_c.id]
}

output "s3_bucket_name" {
  description = "사용한 S3 버킷 이름"
  value       = data.aws_s3_bucket.frontend.id
}

output "s3_website_endpoint" {
  description = "프론트엔드 접속 주소 (이 주소로 브라우저에서 확인)"
  value       = aws_s3_bucket_website_configuration.frontend.website_endpoint
}

# =================================
# 2단계 출력 (Backend)
# =================================

output "alb_dns_name" {
  description = "백엔드 API 서버 주소 (ALB DNS). api.chxtwo.kro.kr를 이 주소로 CNAME 연결하세요."
  value       = aws_lb.main.dns_name
}

output "ecr_repository_url" {
  description = "GitHub Actions CI/CD가 Docker 이미지를 푸시할 ECR 리포지토리 주소"
  value       = aws_ecr_repository.app.repository_url
}

output "db_hostname" {
  description = "Flask 앱이 연결할 RDS MySQL 데이터베이스 주소"
  value       = aws_db_instance.main.address
}

output "db_name" {
  description = "Flask 앱이 연결할 데이터베이스 이름"
  value       = aws_db_instance.main.db_name
}

output "db_username" {
  description = "Flask 앱이 연결할 데이터베이스 사용자 이름"
  value       = aws_db_instance.main.username
}
