# Throwaway GPU training box for the capacity-planning demo.
#
# Everything environment-specific (region, instance type, SSH CIDR, key path) comes from
# TF_VAR_* variables - copy ../.env.example to ../.env, fill it in, then:
#
#   cd infra
#   set -a; source ../.env; set +a
#   terraform init && terraform apply
#
# The AWS account/profile is whatever your ambient credentials resolve to (AWS_PROFILE
# in ../.env). Destroy the instance when you are done: terraform destroy.

terraform {
  required_version = ">= 1.5"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.0"
    }
  }
}

provider "aws" {
  region = var.region
}

# Latest AWS Deep Learning Base AMI: NVIDIA drivers + CUDA preinstalled, nothing else -
# the runner script installs uv and the project on first use.
data "aws_ami" "dl_gpu" {
  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["Deep Learning Base OSS Nvidia Driver GPU AMI (Ubuntu 22.04)*"]
  }

  filter {
    name   = "architecture"
    values = ["x86_64"]
  }
}

data "aws_vpc" "default" {
  default = true
}

resource "aws_key_pair" "training" {
  key_name   = "${var.name_prefix}-key"
  public_key = file(pathexpand(var.public_key_path))
}

resource "aws_security_group" "training" {
  name        = "${var.name_prefix}-sg"
  description = "SSH-only access to the demo training box"
  vpc_id      = data.aws_vpc.default.id

  ingress {
    description = "SSH from your address only"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = [var.allowed_ssh_cidr]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_instance" "training" {
  ami                    = data.aws_ami.dl_gpu.id
  instance_type          = var.instance_type
  key_name               = aws_key_pair.training.key_name
  vpc_security_group_ids = [aws_security_group.training.id]

  # Explicit: default subnets do not always auto-assign public IPs, and without one
  # there is nothing to SSH to.
  associate_public_ip_address = true

  # The DL AMI snapshot alone needs >100 GB; leave room for datasets and wheels.
  root_block_device {
    volume_size = 200
    volume_type = "gp3"
  }

  # IMDSv2 only.
  metadata_options {
    http_tokens = "required"
  }

  tags = {
    Name    = var.name_prefix
    Project = "gpu-capacity-planning-demo"
  }
}

# Some accounts strip or never assign auto public IPs on default subnets; an EIP is
# deterministic either way. Free while associated with a running instance.
resource "aws_eip" "training" {
  domain = "vpc"

  tags = {
    Name    = var.name_prefix
    Project = "gpu-capacity-planning-demo"
  }
}

resource "aws_eip_association" "training" {
  instance_id   = aws_instance.training.id
  allocation_id = aws_eip.training.id
}
