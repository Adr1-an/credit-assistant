FROM node:22-alpine AS build
WORKDIR /app
COPY package*.json ./
# npm ci применяется при наличии зафиксированного lock; в standalone-архиве
# без lock резервно устанавливаем точные прямые версии из package.json.
RUN if [ -f package-lock.json ]; then npm ci; else npm install --no-audit --no-fund; fi
COPY . .
RUN npm run build

FROM nginx:1.27-alpine
COPY nginx/default.conf.template /etc/nginx/templates/default.conf.template
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 3000
CMD ["nginx", "-g", "daemon off;"]
