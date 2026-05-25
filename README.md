# Proyecto-DFS-V2
Sistema de archivos distribuido minimalista basado en bloques, inspirado en HDFS y GFS. Desarrollado como proyecto de la asignatura Tópicos Especiales en Telemática — Sistemas Distribuidos.

---

## Arquitectura

```
                        ┌─────────────────────────┐
                        │        NameNode          │
         ┌──────────────│     FastAPI :8000        │──────────────┐
         │  metadatos   │   JWT · Metadata · Auth  │  heartbeat   │
         │              └─────────────────────────┘              │
         ▼                                                        ▼
   ┌───────────┐      ┌───────────────────────────────────────────────┐
   │  Cliente  │─────▶│  DataNode 1   DataNode 2   DataNode 3        │
   │  CLI      │      │  :8001        :8002         :8003             │
   └───────────┘      │  ./blocks/    ./blocks/     ./blocks/         │
                      └───────────────────────────────────────────────┘
                              │              │
                              └── réplica ──▶│
```

- **NameNode** — servidor central de metadatos. Gestiona el mapa archivo→bloques→DataNodes, autenticación JWT y asignación round-robin de bloques.
- **DataNodes (×3)** — almacenan bloques binarios, envían heartbeat cada 30 s y replican bloques en pipeline.
- **Cliente CLI** — fragmenta archivos en bloques de 64 MB, interactúa con el NameNode para metadatos y transfiere bloques directamente a los DataNodes.

---

## Requisitos

- Docker y Docker Compose v2+
- Python 3.11+ (solo para el cliente CLI local)

---

## Inicio rápido

```bash
# 1. Clonar el repositorio
git clone https://github.com/Jhonnymgx115/Proyecto-DFS-V2.git
cd minidfs

# 2. Configurar variables de entorno
cp .env.example .env
# Editar .env y definir JWT_SECRET (obligatorio)
# JWT_SECRET=$(openssl rand -hex 32)

# 3. Levantar el stack completo
docker-compose up --build -d

# 4. Verificar que todos los nodos estén vivos
curl http://localhost:8000/datanodes/status

# 5. Instalar el cliente CLI
pip install -r requirements-client.txt
```

---

## Uso del cliente

```bash
# Registro e inicio de sesión
minidfs register --user jorge --pass secreto
minidfs login    --user jorge --pass secreto

# Subir un archivo (se parte en bloques de 64 MB automáticamente)
minidfs put ./video_grande.mp4

# Listar archivos
minidfs ls

# Descargar un archivo (se reconstruye desde los bloques)
minidfs get video_grande.mp4 ./descargado.mp4

# Eliminar un archivo
minidfs rm video_grande.mp4

# Gestión de directorios
minidfs mkdir proyectos
minidfs rmdir proyectos

# Ver estado de los DataNodes
minidfs status
```

---

## Variables de entorno

| Variable | Descripción | Por defecto |
|---|---|---|
| `JWT_SECRET` | Clave para firmar tokens JWT | **requerida** |
| `BLOCK_SIZE_MB` | Tamaño de bloque en MB | `64` |
| `REPLICATION_FACTOR` | Réplicas por bloque | `2` |
| `NAMENODE_URL` | URL del NameNode | `http://namenode:8000` |
| `DATANODE_ID` | Identificador del DataNode | `dn1` / `dn2` / `dn3` |
| `HEARTBEAT_INTERVAL` | Segundos entre heartbeats | `30` |
| `METADATA_FILE` | Ruta del archivo de metadatos | `namenode_metadata.json` |

---

## Estructura del repositorio

```
minidfs/
├── namenode/              # Servidor de metadatos (Persona 1)
│   ├── main.py            # FastAPI app, endpoints REST
│   ├── auth.py            # JWT, bcrypt, dependencias de auth
│   ├── metadata.py        # MetadataStore con persistencia JSON
│   ├── block_manager.py   # Algoritmo de asignación y resolución
│   ├── schemas.py         # Modelos Pydantic
│   ├── config.py          # Variables de entorno
│   └── Dockerfile
├── datanode/              # Nodo de almacenamiento (Persona 2)
│   ├── main.py            # FastAPI app, endpoints REST
│   ├── storage.py         # I/O de bloques con aiofiles
│   ├── replication.py     # Pipeline push/pull entre DataNodes
│   ├── heartbeat.py       # Background task de reporte
│   ├── config.py
│   └── Dockerfile
├── client/                # CLI del usuario (Persona 3)
│   ├── cli.py             # Comandos Typer
│   ├── file_ops.py        # Lógica put/get con barra de progreso
│   ├── auth_client.py     # Login y persistencia de token
│   └── config.py
├── tests/
│   ├── test_namenode.py   # Tests unitarios NameNode
│   ├── test_datanode.py   # Tests unitarios DataNode
│   ├── test_integration.py# Tests de integración completos
│   ├── conftest.py        # Fixtures pytest
│   └── test_e2e.sh        # Test end-to-end con verificación SHA256
├── docs/
│   └── TROUBLESHOOTING.md # Guía de errores conocidos y soluciones
├── scripts/
│   └── run_tests.sh       # Script de CI: levanta stack + corre tests
├── docker-compose.yml
├── docker-compose.test.yml
├── .env.example
├── requirements-namenode.txt
├── requirements-datanode.txt
├── requirements-client.txt
└── README.md
```

---

## Pruebas

```bash
# Tests unitarios (sin Docker)
pytest tests/test_namenode.py tests/test_datanode.py -v

# Tests de integración (requiere stack levantado)
docker-compose up -d
pytest tests/test_integration.py -v

# Test end-to-end con archivo de 200 MB y verificación de checksum
bash tests/test_e2e.sh

# Suite completa automatizada
bash scripts/run_tests.sh
```

---

## Flujo de trabajo Git

| Rama | Propósito |
|---|---|
| `main` | Versión estable, protegida. Solo merge desde `dev`. |
| `dev` | Integración continua. Todos los commits van aquí primero. |
| `fix` | Simulación de bugs conocidos + soluciones documentadas. No se fusiona a `main`. |

```bash
# Flujo de contribución
git checkout dev
git pull origin dev
# ... commits ...
git push origin dev
# Pull Request dev → main cuando la feature está completa
```

---

## Ramas y contribuciones

| Persona | Responsabilidad | Commits en dev |
|---|---|---|
| Persona 1 | NameNode, Auth, Metadata | 12 commits |
| Persona 2 | DataNode, Replicación, Heartbeat | 12 commits |
| Persona 3 | Cliente CLI, Docker, Tests, Rama fix | 11 + 6 commits |

---

## Referencia rápida de la API

**NameNode** `http://localhost:8000`

| Endpoint | Descripción |
|---|---|
| `POST /auth/login` | Obtener token JWT |
| `POST /files/put` | Solicitar plan de bloques |
| `GET /files/get/{filename}` | Obtener ubicación de bloques |
| `GET /files/ls` | Listar archivos del usuario |
| `GET /datanodes/status` | Estado de salud de los DataNodes |

**DataNode** `http://localhost:8001` (también 8002, 8003)

| Endpoint | Descripción |
|---|---|
| `POST /blocks/upload/{id}` | Subir bloque binario |
| `GET /blocks/download/{id}` | Descargar bloque binario |
| `POST /blocks/replicate/{id}` | Replicar bloque a otro DataNode |

---

## Licencia

Proyecto académico — Escuela de Ingenierías y Ciencias, 2026 - MIT.
