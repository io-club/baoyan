ARG JRE_IMAGE=eclipse-temurin:17-jre-alpine
FROM ${JRE_IMAGE}

RUN addgroup -S gateway && adduser -S -G gateway gateway
WORKDIR /app
COPY target/gateway.jar /app/gateway.jar
RUN chown -R gateway:gateway /app

USER gateway
EXPOSE 8080
ENTRYPOINT ["java", "-XX:MaxRAMPercentage=75", "-jar", "/app/gateway.jar"]

