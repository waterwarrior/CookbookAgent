locals {
  function_name = "${var.name}-webhook"
  source_bucket = "${var.project_id}-${var.name}-source"
}

resource "google_project_service" "apis" {
  for_each = toset([
    "aiplatform.googleapis.com",
    "artifactregistry.googleapis.com",
    "cloudbuild.googleapis.com",
    "cloudfunctions.googleapis.com",
    "eventarc.googleapis.com",
    "firestore.googleapis.com",
    "run.googleapis.com",
    "secretmanager.googleapis.com",
    "storage.googleapis.com",
  ])

  project            = var.project_id
  service            = each.value
  disable_on_destroy = false
}

resource "google_firestore_database" "default" {
  count = var.create_firestore_database ? 1 : 0

  project                     = var.project_id
  name                        = var.firestore_database_id
  location_id                 = var.firestore_location
  type                        = "FIRESTORE_NATIVE"
  concurrency_mode            = "OPTIMISTIC"
  app_engine_integration_mode = "DISABLED"

  depends_on = [
    google_project_service.apis["firestore.googleapis.com"],
  ]
}

resource "google_secret_manager_secret" "telegram_token" {
  project   = var.project_id
  secret_id = "${var.name}-telegram-token"

  replication {
    auto {}
  }

  depends_on = [
    google_project_service.apis["secretmanager.googleapis.com"],
  ]
}

resource "google_secret_manager_secret_version" "telegram_token" {
  secret      = google_secret_manager_secret.telegram_token.id
  secret_data = var.telegram_bot_token
}

resource "google_service_account" "function" {
  project      = var.project_id
  account_id   = "${var.name}-fn"
  display_name = "SmartCookbook Cloud Function"
}

resource "google_project_iam_member" "function_vertex_user" {
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.function.email}"
}

resource "google_project_iam_member" "function_firestore_user" {
  project = var.project_id
  role    = "roles/datastore.user"
  member  = "serviceAccount:${google_service_account.function.email}"
}

resource "google_project_iam_member" "function_logs_writer" {
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.function.email}"
}

resource "google_secret_manager_secret_iam_member" "function_secret_accessor" {
  project   = var.project_id
  secret_id = google_secret_manager_secret.telegram_token.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.function.email}"
}

resource "google_storage_bucket" "function_source" {
  project                     = var.project_id
  name                        = local.source_bucket
  location                    = var.region
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = true

  depends_on = [
    google_project_service.apis["storage.googleapis.com"],
  ]
}

data "archive_file" "function_source" {
  type        = "zip"
  source_dir  = "${path.module}/function"
  output_path = "${path.module}/function.zip"
}

resource "google_storage_bucket_object" "function_source" {
  name   = "source/${local.function_name}-${data.archive_file.function_source.output_md5}.zip"
  bucket = google_storage_bucket.function_source.name
  source = data.archive_file.function_source.output_path
}

resource "google_cloudfunctions2_function" "webhook" {
  project     = var.project_id
  name        = local.function_name
  location    = var.region
  description = "Telegram webhook for the SmartCookbook AI bot."

  build_config {
    runtime     = "python312"
    entry_point = "telegram_webhook"

    source {
      storage_source {
        bucket = google_storage_bucket.function_source.name
        object = google_storage_bucket_object.function_source.name
      }
    }
  }

  service_config {
    available_memory      = "512Mi"
    timeout_seconds       = 60
    max_instance_count    = var.max_instance_count
    min_instance_count    = 0
    ingress_settings      = "ALLOW_ALL"
    service_account_email = google_service_account.function.email

    environment_variables = {
      ALLOWED_CHATS       = join(",", var.allowed_telegram_user_ids)
      FIRESTORE_DATABASE  = var.firestore_database_id
      GEMINI_TEXT_MODEL   = var.gemini_text_model
      GEMINI_VISION_MODEL = var.gemini_vision_model
      LANGUAGE            = var.bot_language
      PROJECT_ID          = var.project_id
      RECIPES_COLLECTION  = var.recipes_collection
      SESSIONS_COLLECTION = var.sessions_collection
      VERTEX_LOCATION     = var.region
    }

    secret_environment_variables {
      key        = "TELEGRAM_TOKEN"
      project_id = var.project_id
      secret     = google_secret_manager_secret.telegram_token.secret_id
      version    = "latest"
    }
  }

  depends_on = [
    google_project_iam_member.function_firestore_user,
    google_project_iam_member.function_logs_writer,
    google_project_iam_member.function_vertex_user,
    google_project_service.apis["artifactregistry.googleapis.com"],
    google_project_service.apis["cloudbuild.googleapis.com"],
    google_project_service.apis["cloudfunctions.googleapis.com"],
    google_project_service.apis["eventarc.googleapis.com"],
    google_project_service.apis["run.googleapis.com"],
    google_secret_manager_secret_iam_member.function_secret_accessor,
  ]
}

resource "google_cloud_run_v2_service_iam_member" "public_invoker" {
  project  = var.project_id
  location = google_cloudfunctions2_function.webhook.location
  name     = google_cloudfunctions2_function.webhook.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}
