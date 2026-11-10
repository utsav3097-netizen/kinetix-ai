output "cluster_name" {
  description = "ECS cluster for one-shot migration and service deployments."
  value       = aws_ecs_cluster.main.name
}

output "web_service_name" {
  description = "ECS web service name."
  value       = aws_ecs_service.web.name
}

output "worker_service_name" {
  description = "ECS AI worker service name."
  value       = aws_ecs_service.worker.name
}

output "migration_task_definition_arn" {
  description = "Task definition ARN to run once before each service deployment."
  value       = aws_ecs_task_definition.migration.arn
}

output "web_task_definition_arn" {
  description = "Immutable web task definition ARN for post-migration ECS service update."
  value       = aws_ecs_task_definition.web.arn
}

output "worker_task_definition_arn" {
  description = "Immutable worker task definition ARN for post-migration ECS service update."
  value       = aws_ecs_task_definition.worker.arn
}

output "load_balancer_dns_name" {
  description = "CloudFront origin ALB DNS name."
  value       = aws_lb.main.dns_name
}

output "target_group_arn" {
  description = "ALB target group ARN for deployment health verification."
  value       = aws_lb_target_group.web.arn
}

output "ecr_repository_name" {
  description = "Immutable KINETIX container repository name."
  value       = data.aws_ecr_repository.app.name
}

output "ecr_repository_url" {
  description = "Registry URL used to push immutable release images."
  value       = data.aws_ecr_repository.app.repository_url
}

output "cloudfront_domain_name" {
  description = "Generated HTTPS CloudFront distribution hostname."
  value       = aws_cloudfront_distribution.site.domain_name
}

output "cloudfront_url" {
  description = "Public HTTPS URL for this environment."
  value       = "https://${aws_cloudfront_distribution.site.domain_name}"
}

output "migration_subnet_ids" {
  description = "Private subnet IDs for running the migration task."
  value       = aws_subnet.private[*].id
}

output "task_security_group_id" {
  description = "Task security group ID for one-shot migration networking."
  value       = aws_security_group.tasks.id
}

output "alb_security_group_id" {
  description = "ALB security group ID."
  value       = aws_security_group.alb.id
}

output "application_secret_arn" {
  description = "Secrets Manager ARN containing application runtime keys; value is never output."
  value       = aws_secretsmanager_secret.app.arn
}

output "origin_secret_arn" {
  description = "Secrets Manager ARN for the CloudFront-origin verification secret; value is never output."
  value       = aws_secretsmanager_secret.origin.arn
}

output "database_instance_identifier" {
  description = "Private PostgreSQL RDS instance identifier."
  value       = aws_db_instance.main.identifier
}
