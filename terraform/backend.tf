

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
#resource "random_password" "db_password" {
 # length  = 16
  #special = false # 특수문자 제외 (환경변수 전달 시 단순화)
#}

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
  password             = "qpfmeksel14!2"
  
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
resource "aws_iam_role" "ecs_task_role" {
  name = "project-ecs-task-role"
  
  # ecs-tasks.amazonaws.com 서비스가 이 역할을 맡을 수 있도록 설정
  assume_role_policy = jsonencode({
    Version = "2012-10-17",
    Statement = [{
      Action    = "sts:AssumeRole",
      Effect    = "Allow",
      Principal = { Service = "ecs-tasks.amazonaws.com" }
    }]
  })
}

# [신규] 8-3-1. DynamoDB 읽기 권한 정책 문서
data "aws_iam_policy_document" "ecs_task_dynamodb" {
  statement {
    effect = "Allow"
    actions = [
      "dynamodb:Scan", # app.py의 table.scan()에 필요
      "dynamodb:GetItem",
      "dynamodb:Query"
    ]
    resources = [
      # ⚠️⚠️⚠️ [중요] YOUR_AWS_ACCOUNT_ID 를 찬규님의 12자리 AWS 계정 ID로 변경하세요! ⚠️⚠️⚠️
      "arn:aws:dynamodb:ap-northeast-2:798874239435:table/NaverStockData" 
    ]
  }
}

# [신규] 8-3-2. 위에서 만든 정책을 실제 IAM 정책 리소스로 생성
resource "aws_iam_policy" "ecs_task_dynamodb_policy" {
  name   = "project-ecs-dynamodb-policy"
  policy = data.aws_iam_policy_document.ecs_task_dynamodb.json
}

# [신규] 8-3-3. 생성한 정책을 8-3의 작업 역할(ecs_task_role)에 연결
resource "aws_iam_role_policy_attachment" "ecs_task_dynamodb_attach" {
  role       = aws_iam_role.ecs_task_role.name
  policy_arn = aws_iam_policy.ecs_task_dynamodb_policy.arn
}

# 8-4. ECS 작업 정의 (Task Definition) - ★중요★
resource "aws_ecs_task_definition" "app" {
  family                   = "project-app-task"
  cpu                      = 256  # 0.25 vCPU
  memory                   = 512  # 0.5 GB
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  execution_role_arn       = aws_iam_role.ecs_task_execution_role.arn
  
  task_role_arn            = aws_iam_role.ecs_task_role.arn
  # === 컨테이너 정의 ===
  container_definitions = jsonencode([{
    name  = "project-app-container",
    image = "nginx:latest",
    portMappings = [{
      containerPort = 80, # NGINX 기본 포트 (Flask도 80으로 맞출 예정)
      hostPort      = 80
    }],
    # ----------------------------------------------------------------
        # 🛑 [핵심 수정] command 필드를 명시적으로 추가하여 ECS에 영구 기록
        # ----------------------------------------------------------------
        command = [
            "gunicorn",
            "--bind", "0.0.0.0:80", 
            "--header", "Access-Control-Allow-Origin: *", 
            "--header", "Access-Control-Allow-Credentials: true", 
            "app:app"
        ],
        # ----------------------------------------------------------------
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
# ⬇️ [backend.tf 파일 맨 아래에 추가/수정]

# ===============================================
# 9. RDS 테이블 스키마 자동 생성 (Local-File + Local-Exec)
# ===============================================

# 9-1. 전체 SQL 스키마 파일을 로컬에 생성합니다. (users, posts, comments 포함)
resource "local_file" "init_db_schema" {
  filename = "${path.module}/init_db_schema.sql"
  content  = <<-EOT
    -- 1. 사용자 테이블 (회원가입, 닉네임)
    CREATE TABLE IF NOT EXISTS users (
        user_id INT AUTO_INCREMENT PRIMARY KEY,
        username VARCHAR(50) NOT NULL UNIQUE,
        nickname VARCHAR(50) NOT NULL,
        password_hash VARCHAR(255) NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    
    -- 2. 게시글 테이블
    CREATE TABLE IF NOT EXISTS posts (
        post_id INT AUTO_INCREMENT PRIMARY KEY,
        user_id INT NOT NULL,
        title VARCHAR(255) NOT NULL,
        content TEXT NOT NULL,
        views INT DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    
    -- 3. 댓글 테이블
    CREATE TABLE IF NOT EXISTS comments (
        comment_id INT AUTO_INCREMENT PRIMARY KEY,
        post_id INT NOT NULL,
        user_id INT NOT NULL,
        content TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (post_id) REFERENCES posts(post_id) ON DELETE CASCADE,
        FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
  EOT
}


# 9-2. RDS 인스턴스에 접속하여 SQL 스크립트를 실행합니다.
resource "null_resource" "db_schema_setup" {

  # RDS와 SQL 파일 생성이 완료된 후에 실행되도록 의존성 설정
  depends_on = [aws_db_instance.main, local_file.init_db_schema] 
  
  provisioner "local-exec" {
    # MINGW64 환경에서 Bash 셸을 사용하도록 명시
    interpreter = ["bash", "-c"] 
    
    # 생성된 SQL 파일을 MySQL 클라이언트를 이용해 실행합니다.
    command = <<-EOT
      mysql \
        --host=${aws_db_instance.main.address} \
        --user=${aws_db_instance.main.username} \
        --password="qpfmeksel14!2" \
        --database=${aws_db_instance.main.db_name} \
        < ${path.module}/init_db_schema.sql
    EOT
  }
}