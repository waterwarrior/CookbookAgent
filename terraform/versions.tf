terraform {
  required_version = ">= 1.6.0"

  required_providers {
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.4"
    }

    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
  }
}
