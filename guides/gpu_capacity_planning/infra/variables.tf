# No environment-specific defaults on purpose: every value below is supplied through
# TF_VAR_* variables sourced from ../.env (see ../.env.example for presets).

variable "region" {
  description = "AWS region for the training box (TF_VAR_region)."
  type        = string
}

variable "instance_type" {
  description = "GPU instance type (TF_VAR_instance_type). The preset g4dn.12xlarge has 4x T4 for a real multi-GPU DDP run."
  type        = string
}

variable "allowed_ssh_cidr" {
  description = "CIDR allowed to SSH in (TF_VAR_allowed_ssh_cidr) - your own address as /32."
  type        = string

  validation {
    condition     = var.allowed_ssh_cidr != "0.0.0.0/0"
    error_message = "Do not open SSH to the whole internet - set your own address, e.g. 203.0.113.7/32."
  }
}

variable "public_key_path" {
  description = "Path to the SSH public key to install on the box (TF_VAR_public_key_path)."
  type        = string
}

variable "name_prefix" {
  description = "Prefix for the AWS resource names."
  type        = string
  default     = "gpu-capacity-demo"
}
