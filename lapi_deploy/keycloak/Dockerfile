# Keycloak for Lapi on OCI: stores its data in the same Autonomous Database (user KEYCLOAK).
# Keycloak ships without the Oracle JDBC driver; add the version its Quarkus (3.15) was
# built against, pinned by checksum (SHA-1 also matches Maven Central's .sha1 files).
#   docker build --platform linux/amd64 -t lapi-local/keycloak:test lapi_deploy/keycloak
ARG KEYCLOAK_VERSION=26.0.7

FROM quay.io/keycloak/keycloak:${KEYCLOAK_VERSION} AS builder
ARG OJDBC_VERSION=23.5.0.24.07
ADD --chown=keycloak:keycloak --chmod=0644 \
    --checksum=sha256:2cc69b821da842c5f5be8877444631cf9fa89561f1f6f5ad7bf1293eb669fc27 \
    https://repo1.maven.org/maven2/com/oracle/database/jdbc/ojdbc11/${OJDBC_VERSION}/ojdbc11-${OJDBC_VERSION}.jar \
    /opt/keycloak/providers/ojdbc11.jar
ADD --chown=keycloak:keycloak --chmod=0644 \
    --checksum=sha256:f447bffd47f391f5e2a839937c5352e0b894c11ffcb7647eb534f8d52a4b2790 \
    https://repo1.maven.org/maven2/com/oracle/database/nls/orai18n/${OJDBC_VERSION}/orai18n-${OJDBC_VERSION}.jar \
    /opt/keycloak/providers/orai18n.jar
# Build-time options: fixed in the optimized image (kc.sh start --optimized).
# One Keycloak in one container instance: local caches, no cluster discovery.
# Sessions are still kept in the database (persistent user sessions, on by default).
ENV KC_DB=oracle \
    KC_CACHE=local \
    KC_HEALTH_ENABLED=true \
    KC_METRICS_ENABLED=false
RUN /opt/keycloak/bin/kc.sh build

FROM quay.io/keycloak/keycloak:${KEYCLOAK_VERSION}
COPY --from=builder /opt/keycloak/ /opt/keycloak/
ENV KC_DB=oracle \
    KC_CACHE=local \
    KC_HEALTH_ENABLED=true \
    KC_METRICS_ENABLED=false
ENTRYPOINT ["/opt/keycloak/bin/kc.sh"]
