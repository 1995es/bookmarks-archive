# ---- build stage ----
FROM node:24-alpine AS build

WORKDIR /app

# Left empty by default: an empty VITE_API_URL makes the app derive the backend URL from the
# browser's own hostname at runtime (see frontend/src/api.ts) instead of baking one in here.
ARG VITE_API_URL=
ENV VITE_API_URL=$VITE_API_URL

COPY package.json package-lock.json* ./
RUN npm ci

COPY . .
RUN npm run build

# ---- serve stage ----
FROM nginx:alpine

COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
