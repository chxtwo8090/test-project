variable "region" {
  description = "AWS 리전"
  type        = string
  default     = "ap-northeast-2"
}
variable "project_name" {
  description = "프로젝트의 고유 접두사 (ECR, ECS, S3 리소스 등에 사용됩니다)"
  type        = string
  default     = "chxtwo-project" # 🔑 찬규님의 프로젝트에 맞는 기본값으로 설정
}