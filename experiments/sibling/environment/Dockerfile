FROM golang:1.24.6-bookworm AS go
FROM rust:1.89.0-bookworm AS rust
FROM node:22.18.0-bookworm-slim AS node
FROM mcr.microsoft.com/dotnet/sdk:10.0.100-noble AS sdk10
FROM mcr.microsoft.com/dotnet/sdk:8.0.415-noble
COPY --from=sdk10 /usr/share/dotnet/ /usr/share/dotnet/
COPY --from=go /usr/local/go /usr/local/go
COPY --from=rust /usr/local/rustup /usr/local/rustup
COPY --from=rust /usr/local/cargo/bin /usr/local/cargo/bin
COPY --from=node /usr/local/bin/node /usr/local/bin/node
COPY --from=node /usr/local/lib/node_modules/npm /usr/local/lib/node_modules/npm
ENV RUSTUP_HOME=/usr/local/rustup DOTNET_NOLOGO=1 DOTNET_CLI_TELEMETRY_OPTOUT=1
ENV PATH=/opt/venv/bin:/opt/deps/node_modules/.bin:/usr/local/go/bin:/usr/local/cargo/bin:${PATH}
RUN apt-get update && apt-get install -y --no-install-recommends python3-venv build-essential ripgrep git ca-certificates && rm -rf /var/lib/apt/lists/* && ln -s /usr/local/lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm
COPY code /opt/b
RUN python3 -m venv /opt/venv && pip install -e /opt/b lark==1.3.1 mypy==2.4.1 && dotnet build /opt/b/dotnet/B.CsHost/B.CsHost.csproj -c Release && dotnet build /opt/b/dotnet/B.NetHost/B.NetHost.csproj -c Release
RUN B_CACHE_DIR=/opt/seed-cache python -c "from b_lang.csadapter import _host; _host()"
COPY package*.json /opt/deps/
RUN cd /opt/deps && npm ci --no-audit --no-fund && npm install -g @anthropic-ai/claude-code@2.1.331 && claude --version && go version && cargo -V && tsc -v && mypy --version
WORKDIR /work
