include custom.mk

gcp-build:  ## Build your docker container for Google Cloud
	@docker build -t ${IMAGE_URL} . -f Dockerfile.web --platform linux/amd64

gcp-push:  ## Push your docker container for Google Cloud
	@docker push ${IMAGE_URL}

gcp-deploy:  ## Deploy the latest docker container to Google Cloud
	@gcloud run deploy bh-crypto-web \
	--region ${REGION} \
	--update-env-vars DJANGO_SETTINGS_MODULE=bh_crypto.settings_production \
	--image ${IMAGE_URL} \
	--set-cloudsql-instances ${DATABASE_ADDRESS} \
	--network ${REDIS_NETWORK} \
	--set-secrets APPLICATION_SETTINGS=application_settings:latest \
	--service-account ${SERVICE_ACCOUNT} \
	--allow-unauthenticated

gcp-full-deploy: gcp-build gcp-push gcp-deploy  ## Build, push, and deploy the latest code to Google Cloud

gcp-sql-shell:  ## Get a Google Cloud SQL shell
	gcloud sql connect ${DATABASE_INSTANCE_NAME} --user=${DATABASE_USER} --database=${DATABASE_NAME}

.PHONY: help
.DEFAULT_GOAL := help

help:
	@grep -hE '^[a-zA-Z0-9_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-30s\033[0m %s\n", $$1, $$2}'

# catch-all for any undefined targets - this prevents error messages
# when running things like make npm-install <package>
%:
	@:
