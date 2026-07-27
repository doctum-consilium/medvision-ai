# Image de l'interface web MedVision.
#
# POURQUOI une image séparée de `medvision-ai` : celle-ci pèse plusieurs
# gigaoctets (PyTorch, TensorFlow, ONNX Runtime). Y ajouter le front
# obligerait à la reconstruire à chaque retouche de bouton. Ici, l'image
# finale ne contient que du HTML, du CSS, du JavaScript et nginx — une
# quarantaine de mégaoctets, reconstruits en moins d'une minute.
#
# Construction en deux étapes : Node compile, nginx sert. Node et les 400 Mo
# de `node_modules` ne partent jamais en production.

# ── Étape 1 : compilation ────────────────────────────────────────────────
FROM node:22-alpine AS build

WORKDIR /build

# Les manifestes d'abord, le code ensuite : tant que les dépendances ne
# changent pas, Docker réutilise la couche d'installation et le build ne
# refait que la compilation.
COPY frontend/package.json frontend/package-lock.json ./
# `npm ci` installe EXACTEMENT le contenu du lock et échoue si le lock est
# désynchronisé — ce qui évite qu'une version différente de celle testée en
# intégration continue se retrouve en production.
RUN npm ci

COPY frontend/ ./
RUN npm run build

# ── Étape 2 : service ────────────────────────────────────────────────────
FROM nginx:1.27-alpine

# Configuration maison : mono-page + proxy vers l'API + flux temps réel.
# Déposée comme GABARIT : le point d'entrée officiel de l'image nginx y
# substitue les deux variables ci-dessous avant de démarrer le serveur.
COPY docker/nginx-frontend.conf.template /etc/nginx/templates/default.conf.template
COPY --from=build /build/dist/medvision-web/browser /usr/share/nginx/html

# Fait écrire le DNS du cluster (lu dans /etc/resolv.conf) dans
# $NGINX_LOCAL_RESOLVERS. Sans ce drapeau, la variable reste vide et la
# configuration devient invalide.
ENV NGINX_ENTRYPOINT_LOCAL_RESOLVERS=1

# Adresse de l'API. Surchargeable par le ConfigMap k3s sans reconstruire
# l'image (utile pour pointer une API de recette).
ENV MEDVISION_API_UPSTREAM=http://medvision-api:8000

# Restreint la substitution à NOS deux variables : sans ce garde-fou,
# envsubst pourrait toucher à autre chose dans le gabarit.
ENV NGINX_ENVSUBST_FILTER="^(NGINX_LOCAL_RESOLVERS|MEDVISION_API_UPSTREAM)$"

EXPOSE 80

# Vérification de vie : si nginx ne rend plus la page, k3s doit le savoir.
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s \
  CMD wget -q --spider http://127.0.0.1/ || exit 1
