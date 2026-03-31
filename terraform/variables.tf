variable "project_id" {
  description = "GCP project ID (e.g. my-project-123)"
  type        = string
}

variable "region" {
  description = "GCP region for all resources"
  type        = string
  default     = "australia-southeast2"
}

variable "max_instances" {
  description = "Maximum number of Cloud Run instances (controls cost ceiling)"
  type        = number
  default     = 3
}

variable "domain" {
  description = "Custom domain to serve (e.g. sixdegreesofmovies.com)"
  type        = string
  default     = "sixdegreesofmovies.com"
}

variable "cloudflare_api_token" {
  description = "Cloudflare API token with Workers Scripts:Edit, Workers Routes:Edit, DNS:Edit permissions"
  type        = string
  sensitive   = true
}

variable "cloudflare_account_id" {
  description = "Cloudflare account ID (found in the Cloudflare dashboard sidebar)"
  type        = string
}

variable "cloudflare_zone_id" {
  description = "Cloudflare zone ID for the domain (found in the domain's Overview page)"
  type        = string
}
