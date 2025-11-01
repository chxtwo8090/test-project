

# ===============================================
# 4. 보안 그룹 (Security Group)
# ===============================================

# [요청 사항] 테스트를 위해 모든 트래픽을 허용하는 보안 그룹
resource "aws_security_group" "allow_all" {
  name        = "project-allow-all"
  description = "Allow all inbound/outbound traffic (TESTING ONLY)"
  vpc_id      = aws_vpc.main.id # 1단계에서 생성한 VPC ID 참조

  ingress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1" # 모든 프로토콜
    cidr_blocks = ["0.0.0.0/0"]
  }
  
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
  
  tags = {
    Name = "project-sg-allow-all"
  }
}

# ===============================================
# 5. 데이터베이스 (RDS)
# ===============================================

# 5-1. DB 마스터 암호 생성
resource "random_password" "db_password" {
  length  = 16
  special = false # 특수문자 제외 (환경변수 전달 시 단순화)
}

# 5-2. RDS 서브넷 그룹
resource "aws_db_subnet_group" "rds_subnet_group" {
  name       = "project-rds-subnet-group"
  subnet_ids = [aws_subnet.public_a.id, aws_subnet.public_c.id] # 1단계의 퍼블릭 서브넷 참조

  tags = {
    Name = "project-rds-subnets"
  }
}

# 5-3. RDS MySQL 인스턴스 (Free Tier)
resource "aws_db_instance" "main" {
  identifier           = "project-db"
  engine               = "mysql"
  engine_version       = "8.0"
  instance_class       = "db.t3.micro" # Free Tier
  allocated_storage    = 20            # 20GB
  
  db_name              = "project_db"  # Flask가 연결할 데이터베이스 이름
  username             = "admin"
  password             = random_password.db_password.result
  
  db_subnet_group_name   = aws_db_subnet_group.rds_subnet_group.name
  vpc_security_group_ids = [aws_security_group.allow_all.id] # 모든 트래픽 허용 SG
  publicly_accessible  = true # 모든 트래픽 허용 설정과 맞춤
  skip_final_snapshot  = true
}

# ===============================================
# 6. 컨테이너 레지스트리 (ECR)
# ===============================================

# 6-1. Flask 앱 Docker 이미지를 저장할 ECR 리포지토리
resource "aws_ecr_repository" "app" {
  name = "project-app-repo" # CI/CD에서 사용할 리포지토리 이름
}

# ===============================================
# 7. 로드 밸런서 (ALB)
# ===============================================

# 7-1. ALB (Application Load Balancer)
resource "aws_lb" "main" {
  name               = "project-alb"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [aws_security_group.allow_all.id] # 모든 트래픽 허용 SG
  subnets            = [aws_subnet.public_a.id, aws_subnet.public_c.id] # 1단계의 퍼블릭 서브넷 참조
}

# 7-2. ALB 타겟 그룹 (ECS 컨테이너로 트래픽 전달)
resource "aws_lb_target_group" "app" {
  name        = "project-app-tg"
  port        = 80 # Flask가 80번 포트로 실행된다고 가정
  protocol    = "HTTP"
  vpc_id      = aws_vpc.main.id # 1단계 VPC 참조
  target_type = "ip"            # ECS Fargate는 ip 타입 사용
}

# 7-3. ALB 리스너 (80번 포트(HTTP)로 들어오는 트래픽을 타겟 그룹으로 전달)
resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.main.arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.app.arn
  }
}

# ===============================================
# 8. 컨테이너 실행 (ECS)
# ===============================================

# 8-1. ECS 클러스터 (컨테이너들의 논리적 그룹)
resource "aws_ecs_cluster" "main" {
  name = "project-cluster"
}

# 8-2. ECS가 ECR에서 이미지를 당겨올 수 있도록 하는 IAM 역할
resource "aws_iam_role" "ecs_task_execution_role" {
  name = "project-ecs-execution-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17",
    Statement = [{
      Action    = "sts:AssumeRole",
      Effect    = "Allow",
      Principal = { Service = "ecs-tasks.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "ecs_execution_policy" {
  role       = aws_iam_role.ecs_task_execution_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

# 8-3. ECS 로그 그룹 (디버깅용)
resource "aws_cloudwatch_log_group" "ecs" {
  name              = "/ecs/project-app-task"
  retention_in_days = 7 # 7일간 로그 보관
}

# 8-4. ECS 작업 정의 (Task Definition) - ★중요★
resource "aws_ecs_task_definition" "app" {
  family                   = "project-app-task"
  cpu                      = 256  # 0.25 vCPU
  memory                   = 512  # 0.5 GB
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  execution_role_arn       = aws_iam_role.ecs_task_execution_role.arn
  
  # === 컨테이너 정의 ===
  container_definitions = jsonencode([{
    name  = "project-app-container",
    # [임시] NGINX 이미지로 설정. CI/CD 파이프라인이
    # 이 부분을 실제 Flask 앱 이미지(aws_ecr_repository.app.repository_url)로
    # 덮어쓰고 환경변수(DB 정보)를 주입할 것입니다.
    image = "nginx:latest",
    portMappings = [{
      containerPort = 80, # NGINX 기본 포트 (Flask도 80으로 맞출 예정)
      hostPort      = 80
    }],
    # 로그 설정을 8-3에서 만든 로그 그룹으로 보냅니다.
    logConfiguration = {
       logDriver = "awslogs",
       options = {
         "awslogs-group"         = aws_cloudwatch_log_group.ecs.name,
         "awslogs-region"        = var.region,
         "awslogs-stream-prefix" = "ecs-app"
       }
    }
  }])
}

# 8-5. ECS 서비스
resource "aws_ecs_service" "app" {
  name            = "project-app-service"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.app.arn
  launch_type     = "FARGATE"
  desired_count   = 1 # 우선 1개의 컨테이너만 실행

  # 1단계에서 만든 퍼블릭 서브넷에 배포
  network_configuration {
    subnets         = [aws_subnet.public_a.id, aws_subnet.public_c.id]
    security_groups = [aws_security_group.allow_all.id]
    assign_public_ip = true # 퍼블릭 서브넷에서 ECR 이미지를 당겨오기 위해 필요
  }
  
  # 7-2에서 만든 ALB 타겟 그룹과 연결
  load_balancer {
    target_group_arn = aws_lb_target_group.app.arn
    container_name   = "project-app-container"
    container_port   = 80
  }
  
  # ALB가 준비된 후 서비스를 시작하도록 보장
  depends_on = [aws_lb_listener.http]
}