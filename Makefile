IMAGE_NAME = spyroot/dpdk-pktgen-k8s-cycling-bench
DOCKER_TAG = latest
ARCHS = amd64 arm64

all: build

build: $(ARCHS)

$(ARCHS):
	@echo "Building Docker image for architecture $@..."
	@if docker buildx version > /dev/null 2>&1; then \
		docker buildx build --platform linux/$@ -t $(IMAGE_NAME):$(DOCKER_TAG) .; \
	else \
		docker build -t $(IMAGE_NAME):$(DOCKER_TAG) .; \
	fi

push:
	docker push $(IMAGE_NAME):$(DOCKER_TAG)

clean:
	docker builder prune -f

.PHONY: all build push clean
