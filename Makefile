# Define the base name for the image
IMAGE_NAME = dpdk-pktgen-k8s-cycling-bench
DOCKER_TAG = latest
ARCHS = amd64 arm64
all: build

build: $(ARCHS)

$(ARCHS):
	@echo "Building Docker image for architecture $@..."
	docker buildx build --platform linux/$@ -t $(IMAGE_NAME):$(DOCKER_TAG) .

push:
	docker push $(IMAGE_NAME):$(DOCKER_TAG)

clean:
	docker builder prune -f

.PHONY: all build push clean
