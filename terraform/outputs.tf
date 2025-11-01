output "vpc_id" {
  description = "생성된 VPC의 ID"
  value       = aws_vpc.main.id
}

output "public_subnet_ids" {
  description = "생성된 퍼블릭 서브넷 ID 목록 (ALB, ECS 배치용)"
  value       = [aws_subnet.public_a.id, aws_subnet.public_c.id]
}

output "s3_bucket_name" {
  description = "프론트엔드 파일(HTML 등)을 업로드할 S3 버킷 이름"
  value       = aws_s3_bucket.frontend.id
}

output "cloudfront_domain" {
  description = "프론트엔드 접속 주소 (이 주소로 브라우저에서 확인)"
  value       = aws_cloudfront_distribution.frontend.domain_name
}