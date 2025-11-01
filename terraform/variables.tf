variable "aws_region" {
  description = "EKS 클러스터를 배포할 AWS 리전"
  type        = string
  default     = "ap-northeast-2" # 서울 리전
}

variable "cluster_name" {
  description = "EKS 클러스터의 고유 이름"
  type        = string
  default     = "project-cluster" # 원하시는 이름으로 변경
}

variable "vpc_cidr" {
  description = "VPC가 사용할 IP 대역"
  type        = string
  default     = "10.0.0.0/16"
}