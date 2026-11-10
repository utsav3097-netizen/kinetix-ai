variable "aws_region" {
  type    = string
  default = "ap-south-1"
}

variable "environment" {
  type = string
  validation {
    condition     = contains(["staging", "production"], var.environment)
    error_message = "environment must be staging or production"
  }
}

variable "image_digest" {
  type        = string
  default     = null
  description = "Immutable image digest, e.g. sha256:...; required for task-definition registration."
  validation {
    condition     = var.image_digest == null || can(regex("^sha256:[0-9a-f]{64}$", var.image_digest))
    error_message = "image_digest must be an immutable sha256 digest when supplied."
  }
}

variable "gemini_api_key" {
  type      = string
  sensitive = true
  default   = ""
}

variable "openai_api_key" {
  type      = string
  sensitive = true
  default   = ""
}

variable "alarm_email" {
  type    = string
  default = ""
}

variable "web_min_capacity" {
  type    = number
  default = 2
}

variable "web_max_capacity" {
  type    = number
  default = 10
}
