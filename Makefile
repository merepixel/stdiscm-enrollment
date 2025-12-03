PY ?= python3
PROTO_SRC := $(wildcard proto/*.proto)
PROTO_OUT := common/protos

.PHONY: protos
protos:
	mkdir -p $(PROTO_OUT)
	$(PY) -m grpc_tools.protoc -I proto --python_out=$(PROTO_OUT) --grpc_python_out=$(PROTO_OUT) $(PROTO_SRC)

.PHONY: smoke
smoke:
	./scripts/smoke.sh

.PHONY: ci
ci: protos
	cd infra && docker compose up -d --build
	./scripts/smoke.sh
	pytest tests/test_smoke.py
	cd infra && docker compose down -v
