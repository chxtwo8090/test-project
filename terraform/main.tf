 terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.0"
    }
  }
}

provider "aws" {
  region = var.region
}

# ===============================================
# 2. 네트워크 (VPC) - [이전과 동일]
# ===============================================
resource "aws_vpc" "main" {
  cidr_block = "10.0.0.0/16"
  
  enable_dns_support   = true 
  enable_dns_hostnames = true
  
  tags = {
    Name = "project-vpc"
  }
}

# 2-1. 퍼블릭 서브넷 (서울 2a, 2c 리전)
resource "aws_subnet" "public_a" {
  vpc_id            = aws_vpc.main.id
  cidr_block        = "10.0.1.0/24"
  availability_zone = "ap-northeast-2a"
  map_public_ip_on_launch = true
  tags = {
    Name = "project-public-subnet-a"
  }
}

resource "aws_subnet" "public_c" {
  vpc_id            = aws_vpc.main.id
  cidr_block        = "10.0.2.0/24"
  availability_zone = "ap-northeast-2c"
  map_public_ip_on_launch = true
  tags = {
    Name = "project-public-subnet-c"
  }
}

# 2-2. 인터넷 게이트웨이 및 라우팅 설정 (이전과 동일)
resource "aws_internet_gateway" "main" {
  vpc_id = aws_vpc.main.id
  
  tags = {
    Name = "project-igw"
  }
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.main.id
  }

  tags = {
    Name = "project-public-rt"
  }
}

resource "aws_route_table_association" "public_a" {
  subnet_id      = aws_subnet.public_a.id
  route_table_id = aws_route_table.public.id
}

resource "aws_route_table_association" "public_c" {
  subnet_id      = aws_subnet.public_c.id
  route_table_id = aws_route_table.public.id
}

# ===============================================
# 3. 프론트엔드 (기존 S3 버킷 설정) - [수정됨]
# ===============================================

# 3-1. [수정] S3 버킷 생성 대신, 기존 버킷 정보 가져오기
data "aws_s3_bucket" "frontend" {
  bucket = "chxtwo-git" 
}

# 3-2. [수정] S3 정적 웹사이트 호스팅 기능 활성화 (대상: data.aws_s3_bucket.frontend)
resource "aws_s3_bucket_website_configuration" "frontend" {
  bucket = data.aws_s3_bucket.frontend.id # 버킷 생성 리소스가 아닌 data를 참조

  index_document {
    suffix = "finance.html" # 기본 문서
  }
}

# 3-3. [수정] S3 버킷 퍼블릭 접근 허용 (차단 해제)
resource "aws_s3_bucket_public_access_block" "frontend" {
  bucket = data.aws_s3_bucket.frontend.id

  block_public_acls       = false
  block_public_policy     = false
  ignore_public_acls      = false
  restrict_public_buckets = false
}

# 3-4. [수정] S3 버킷 정책 (모든 사용자가 읽기 가능하도록 설정)
data "aws_iam_policy_document" "s3_public_policy" {
  statement {
    principals {
      type        = "AWS"
      identifiers = ["*"] # 모든 사용자
    }
    actions   = ["s3:GetObject"] # 읽기
    resources = ["${data.aws_s3_bucket.frontend.arn}/*"] # data로 가져온 버킷 ARN 참조
  }
}

resource "aws_s3_bucket_policy" "frontend" {
  bucket = data.aws_s3_bucket.frontend.id
  policy = data.aws_iam_policy_document.s3_public_policy.json

  # public_access_block이 적용되기 전에 policy가 적용될 수 있도록 의존성 추가
  depends_on = [aws_s3_bucket_public_access_block.frontend]
}
resource "random_string" "llm_tg_suffix" {
  length  = 8
  special = false
  upper   = false
  number  = false
  lifecycle {
    ignore_changes = all
  }
}
# ===============================================
# 7. LLM 모델 S3 참조 및 IAM 권한 설정 (수정됨)
# ===============================================

# 7-1. LLM 모델이 저장된 기존 S3 버킷 'chxtwo-git'의 정보 가져오기
data "aws_s3_bucket" "llm_models" {
  bucket = "chxtwo-git" 
}

# 7-2. 기존 ECS Task Execution Role에 S3 읽기 권한을 추가하기 위한 정책 문서
data "aws_iam_policy_document" "llm_s3_read_policy" {
  statement {
    actions = ["s3:GetObject"]
    resources = ["${data.aws_s3_bucket.llm_models.arn}/*"] 
  }
}

# 7-3. Task Execution Role에 S3 읽기 정책 연결
resource "aws_iam_role_policy" "llm_s3_read_policy_attachment" {
  name   = "llm-s3-read-access"
  role   = aws_iam_role.ecs_task_execution_role.id # 기존 Task Role 참조 가정
  policy = data.aws_iam_policy_document.llm_s3_read_policy.json
}

# ===============================================
# 8. LLM 서비스 로드 밸런싱 (신규)
# ===============================================

# 8-1. LLM 서비스용 타겟 그룹 생성
resource "aws_lb_target_group" "llm_service_tg" {
  name     = "llm-tg-${random_string.llm_tg_suffix.result}"
  port     = 80
  protocol = "HTTP"
  vpc_id   = aws_vpc.main.id
  target_type = "ip"
  lifecycle {
    ignore_changes = [
      load_balancing_algorithm_type,
      deregistration_delay,
      protocol_version
      # 이 외에도 다른 속성이 있다면 추가할 수 있지만, 'ip' 타입 변경 시 문제가 되는
      # 내부 의존성을 Terraform이 무시하도록 돕습니다.
    ]
  }
  health_check {
    path = "/health" 
    protocol = "HTTP"
    matcher = "200"
    interval = 30
    timeout = 5
  }
}

# 8-2. 기존 ALB 리스너에 LLM 경로 규칙 추가
resource "aws_lb_listener_rule" "llm_rule" {
  listener_arn = aws_lb_listener.http.arn 
  priority = 98 

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.llm_service_tg.arn
  }

  condition {
    path_pattern {
      values = ["/llm/*"] 
    }
  }
}

# ===============================================
# 9. LLM Fargate 서비스 배포 (신규)
# ===============================================

# 9-1. LLM 컨테이너 이미지: ECR 리포지토리 설정
resource "aws_ecr_repository" "llm_repository" {
  name                 = "${var.project_name}/llm-api-repo"
  image_tag_mutability = "MUTABLE"
  force_delete         = true 
}

# 9-2. LLM 서비스용 ECS 태스크 정의 (모델 파일명 및 환경 변수 수정)
resource "aws_ecs_task_definition" "llm_task" {
  family                   = "llm-task-family"
  cpu                      = "4096" # 4 vCPU 할당
  memory                   = "8192" # 8 GB 메모리 할당
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  execution_role_arn       = aws_iam_role.ecs_task_execution_role.arn
  task_role_arn            = aws_iam_role.ecs_task_execution_role.arn

  container_definitions = jsonencode([
    {
      name      = "llm-api-container"
      image     = "${aws_ecr_repository.llm_repository.repository_url}:latest" 
      essential = true
      portMappings = [
        {
          containerPort = 80
          hostPort      = 80
        }
      ]
      environment = [
        # S3 다운로드를 위한 환경 변수 주입
        {
            name  = "S3_BUCKET_NAME"
            value = data.aws_s3_bucket.llm_models.id # chxtwo-git
        },
        {
            name  = "S3_MODEL_KEY"
            value = "gemma-3n-E4B-it-Q4_K_M.gguf" # 🔑 수정된 모델 파일 이름
        }
      ]
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.ecs.name
          "awslogs-region"        = var.region
          "awslogs-stream-prefix" = "llm-api-log-stream"
        }
      }
    }
  ])
}

# 9-3. LLM Fargate 서비스 배포 (클러스터 이름 수정)
resource "aws_ecs_service" "llm_service" {
  name            = "llm-fargate-service"
  cluster         = "project-cluster" # 🔑 수정된 클러스터 이름
  task_definition = aws_ecs_task_definition.llm_task.arn
  desired_count   = 1

  launch_type = "FARGATE"

  network_configuration {
    subnets          = [aws_subnet.public_a.id, aws_subnet.public_c.id]
    security_groups  = [aws_security_group.allow_all.id] 
    assign_public_ip = true
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.llm_service_tg.arn
    container_name   = "llm-api-container"
    container_port   = 80
  }
  
  depends_on = [
    aws_lb_listener_rule.llm_rule,
    aws_iam_role_policy.llm_s3_read_policy_attachment
  ]
}