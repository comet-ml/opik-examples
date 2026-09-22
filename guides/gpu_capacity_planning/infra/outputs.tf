output "instance_id" {
  value = aws_instance.training.id
}

output "public_ip" {
  value = aws_eip.training.public_ip

  depends_on = [aws_eip_association.training]
}

output "ssh_command" {
  description = "The DL AMI's login user is ubuntu."
  value       = "ssh ubuntu@${aws_eip.training.public_ip}"

  depends_on = [aws_eip_association.training]
}
