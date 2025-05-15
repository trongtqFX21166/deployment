#!/bin/bash
PRJ=""
IMAGE_TAG="platform.iothub.gateway.api"
VER="1.3.70"
RELEASE_FOLDER=""
# wait k8s export image
REGISTRY_URL="vmapi/hubcentral"

findPRJ() {
     for i in *.csproj; do
          PRJ="${i%.*}"
          # IMAGE_TAG="${PRJ,,}"
          break
     done
}

publishNetCore() {
     RELEASE_FOLDER="bin/release/$PRJ"
     rm -Rf $RELEASE_FOLDER
     mkdir -p $RELEASE_FOLDER
     dotnet publish $PRJ.csproj -c release -o ./$RELEASE_FOLDER/app

     rm -f "$RELEASE_FOLDER/Dockerfile"
     echo "
FROM mcr.microsoft.com/dotnet/aspnet:6.0 AS runtime
WORKDIR /app
COPY /app ./
ENTRYPOINT [\"dotnet\", \"$PRJ.dll\"]
         " > "$RELEASE_FOLDER/Dockerfile"
}

buildDocker () {
     docker rmi -f $IMAGE_TAG.$VER
     docker build -f $RELEASE_FOLDER/Dockerfile -t $IMAGE_TAG.$VER $RELEASE_FOLDER/.
     docker tag $IMAGE_TAG.$VER $REGISTRY_URL:$IMAGE_TAG.$VER
     docker push $REGISTRY_URL:$IMAGE_TAG.$VER
}

startBuild() {
     findPRJ
     publishNetCore
     buildDocker
}

startBuild