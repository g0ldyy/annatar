BUILD_ARCH   ?= linux/amd64
DOCKERFILE   ?= Dockerfile
DOCKER_IMAGE ?= annatar:latest

ifdef CI_REGISTRY_IMAGE
	DOCKER_IMAGE = $(CI_REGISTRY_IMAGE):$(IMAGE_TAG)
endif

# set this to --push if you want the image to be pushed  or --load to just load
# it into the registry
PUSH_OR_LOAD ?= --load

container:
	docker run --rm --privileged multiarch/qemu-user-static --reset -p yes
	docker buildx inspect mybuilder || docker buildx create --use --name mybuilder
	docker buildx inspect --bootstrap
	docker buildx build --platform $(BUILD_ARCH) \
		$(PUSH_OR_LOAD) \
		--cache-from $(DOCKER_IMAGE) \
		--pull \
		-f $(DOCKERFILE) \
		--tag $(DOCKER_IMAGE) \
		--build-arg BUILD_VERSION=$(shell git rev-parse HEAD) \
		.


test:
	poetry run isort --check --diff annatar run.py
	poetry run black --check --diff annatar run.py
	poetry run pytest
