output "function_uri" {
  description = "Base HTTPS URL for the deployed Cloud Function."
  value       = google_cloudfunctions2_function.webhook.service_config[0].uri
}

output "telegram_webhook_url" {
  description = "URL to pass to Telegram setWebhook."
  value       = "${google_cloudfunctions2_function.webhook.service_config[0].uri}/webhook"
}

output "set_webhook_command" {
  description = "Command for registering the Telegram webhook."
  value       = "curl -X POST \"https://api.telegram.org/bot<TELEGRAM_TOKEN>/setWebhook?url=${google_cloudfunctions2_function.webhook.service_config[0].uri}/webhook\""
}
