resource "aws_ecr_repository" "flask_app" {
  name                 = "${var.cluster_name}-flask-app" # ECR 리포지토리 이름
  image_tag_mutability = "MUTABLE" # 태그 덮어쓰기 허용

  image_scanning_configuration {
    scan_on_push = true
  }
}