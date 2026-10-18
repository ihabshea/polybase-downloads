FROM ubuntu:22.04@sha256:0a9887931b0e38af2e3487ed39e29436b0535c4f3f52e57745baaf79d1898956
RUN --mount=type=secret,id=system_ca,required=true \
    --mount=type=secret,id=proxy_ca,required=true \
    cat /run/secrets/system_ca /run/secrets/proxy_ca > /tmp/qualification-ca.pem && \
    apt-get -o Acquire::https::CaInfo=/tmp/qualification-ca.pem update && \
    apt-get -o Acquire::https::CaInfo=/tmp/qualification-ca.pem install -y --no-install-recommends python3 curl ca-certificates && \
    rm -rf /var/lib/apt/lists/* /tmp/qualification-ca.pem
WORKDIR /qualification
