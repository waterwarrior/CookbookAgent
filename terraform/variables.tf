variable "project_id" {
  description = "GCP project ID where the cookbook bot will be deployed."
  type        = string
}

variable "region" {
  description = "Region for Cloud Functions, Cloud Run, Storage, and Vertex AI calls."
  type        = string
  default     = "us-central1"
}

variable "name" {
  description = "Resource name prefix."
  type        = string
  default     = "smart-cookbook"
}

variable "telegram_bot_token" {
  description = "Token received from BotFather."
  type        = string
  sensitive   = true
}

variable "allowed_telegram_user_ids" {
  description = "Telegram chat/user IDs allowed to use the bot."
  type        = list(string)
  default     = []
}

variable "bot_language" {
  description = "Language for bot responses and service messages."
  type        = string
  default     = "RU"

  validation {
    condition     = contains(["EN", "RU"], var.bot_language)
    error_message = "bot_language must be EN or RU."
  }
}

variable "firestore_location" {
  description = "Firestore database location. Use a multi-region such as nam5/eur3, or a supported regional location."
  type        = string
  default     = "nam5"
}

variable "create_firestore_database" {
  description = "Set to false if the project already has a default Firestore database."
  type        = bool
  default     = true
}

variable "firestore_database_id" {
  description = "Firestore database ID used by the Cloud Function."
  type        = string
  default     = "(default)"
}

variable "recipes_collection" {
  description = "Firestore collection for recipes."
  type        = string
  default     = "recipes"
}

variable "sessions_collection" {
  description = "Firestore collection for Telegram chat memory."
  type        = string
  default     = "sessions"
}

variable "gemini_text_model" {
  description = "Vertex AI Gemini model for dialog and tool calling."
  type        = string
  default     = "gemini-2.5-flash"
}

variable "gemini_vision_model" {
  description = "Vertex AI Gemini model for image-to-text recipe extraction."
  type        = string
  default     = "gemini-2.5-flash"
}

variable "max_instance_count" {
  description = "Maximum number of Cloud Function instances."
  type        = number
  default     = 3
}
