CREATE DATABASE IF NOT EXISTS metalurgica_db;
USE metalurgica_db;

-- 1. Tabla de máquinas monitoreadas
CREATE TABLE IF NOT EXISTS maquinas (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nombre VARCHAR(50) NOT NULL UNIQUE,
    tipo VARCHAR(50) NOT NULL,
    ubicacion VARCHAR(100) DEFAULT 'Planta Principal'
);

-- Carga inicial de máquinas industriales
INSERT INTO maquinas (nombre, tipo) VALUES 
('Torno_1', 'Torno'),
('Fresadora_1', 'Fresadora')
ON DUPLICATE KEY UPDATE nombre=nombre;

-- 2. Tabla de Usuarios (Administradores y Operarios)
CREATE TABLE IF NOT EXISTS usuarios (
    id INT AUTO_INCREMENT PRIMARY KEY,
    telegram_id BIGINT UNIQUE NULL,
    nombre VARCHAR(100) NOT NULL,
    username VARCHAR(50) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NULL,
    rol ENUM('ADMIN', 'OPERARIO') NOT NULL DEFAULT 'OPERARIO',
    activo BOOLEAN DEFAULT TRUE,
    fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Carga de usuarios iniciales (Admin + 2 Operarios)
-- Hash de 'admin123'
INSERT INTO usuarios (nombre, username, password_hash, rol) VALUES 
('Administrador Principal', 'admin', '$2b$12$EixZaYVK1fsbw1ZfbX3OXePaWxn96p36WQoeg6Lruj3vjPGga31lW', 'ADMIN'),
('Juan Pérez', 'juan_perez', NULL, 'OPERARIO'),
('Carlos Gómez', 'carlos_gomez', NULL, 'OPERARIO')
ON DUPLICATE KEY UPDATE nombre=nombre;

-- 3. Tabla de Herramientas
CREATE TABLE IF NOT EXISTS herramientas (
    id INT AUTO_INCREMENT PRIMARY KEY,
    maquina_id INT NOT NULL,
    nombre VARCHAR(100) NOT NULL,
    horas_uso DECIMAL(10,2) DEFAULT 0.00,
    horas_expectativa DECIMAL(10,2) NOT NULL,
    ultimo_uso TIMESTAMP NULL,
    FOREIGN KEY (maquina_id) REFERENCES maquinas(id) ON DELETE CASCADE
);

-- Carga inicial de herramientas con maquina/tipo/codigo
INSERT INTO herramientas (maquina_id, nombre, horas_uso, horas_expectativa) VALUES
(1, 'Torno_1 / Inserto de desbaste general / CNMG 120408', 35.58, 60.00),
(1, 'Torno_1 / Inserto de desbaste general / WNMG 080408', 22.40, 60.00),
(1, 'Torno_1 / Inserto de acabado y perfilado / DCMT 11T304', 12.00, 50.00),
(1, 'Torno_1 / Inserto de acabado y perfilado / VBMT 160404', 18.20, 50.00),
(1, 'Torno_1 / Inserto de tronzado y ranurado / MGMN 200', 25.50, 30.00),
(1, 'Torno_1 / Inserto de tronzado y ranurado / MGMN 300', 8.40, 30.00),
(2, 'Fresadora_1 / Mecha helicoidal estándar / DIN 338', 29.67, 40.00),
(2, 'Fresadora_1 / Mecha helicoidal estándar / DIN 1897', 15.30, 40.00),
(2, 'Fresadora_1 / Mecha de centrar / DIN 333-A', 41.20, 50.00),
(2, 'Fresadora_1 / Mecha de centrar / DIN 333-R', 10.50, 50.00),
(2, 'Fresadora_1 / Mecha de puntear (NC Drill) / DIN 1836', 52.80, 60.00),
(2, 'Fresadora_1 / Mecha de puntear (NC Drill) / DIN 6539', 5.20, 60.00)
ON DUPLICATE KEY UPDATE nombre=nombre;

-- 4. Tabla de Asignación Actual de Máquinas
CREATE TABLE IF NOT EXISTS asignaciones_actuales (
    maquina_id INT PRIMARY KEY,
    operario_id INT NULL,
    herramienta_id INT NULL,
    comentario VARCHAR(255) NULL,
    FOREIGN KEY (maquina_id) REFERENCES maquinas(id),
    FOREIGN KEY (operario_id) REFERENCES usuarios(id) ON DELETE SET NULL,
    FOREIGN KEY (herramienta_id) REFERENCES herramientas(id) ON DELETE SET NULL
);

INSERT INTO asignaciones_actuales (maquina_id, operario_id, herramienta_id, comentario) VALUES
(1, 2, 2, 'Operación normal'),
(2, 3, 7, 'Operación normal')
ON DUPLICATE KEY UPDATE maquina_id=maquina_id;

-- 5. Registro de cambios de estado en tiempo real (Telemetría de contactores)
CREATE TABLE IF NOT EXISTS registro_actividad (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    maquina_id INT NOT NULL,
    estado ENUM('ACTIVA', 'PARADA', 'PARADA_EMERGENCIA') NOT NULL,
    codigo_estado TINYINT NOT NULL,
    causa VARCHAR(50) DEFAULT 'OPERACION_NORMAL',
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (maquina_id) REFERENCES maquinas(id) ON DELETE CASCADE,
    INDEX idx_maquina_time (maquina_id, timestamp)
);

-- 6. Tabla de Actividades Consolidadas
CREATE TABLE IF NOT EXISTS actividades (
    id INT AUTO_INCREMENT PRIMARY KEY,
    maquina_id INT NOT NULL,
    operario_id INT NULL,
    herramienta_id INT NULL,
    fecha_inicio TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    fecha_fin TIMESTAMP NULL,
    tiempo_activo_segundos INT DEFAULT 0,
    estado ENUM('EN_CURSO', 'FINALIZADA', 'PARADA_EMERGENCIA') DEFAULT 'EN_CURSO',
    comentario TEXT NULL,
    FOREIGN KEY (maquina_id) REFERENCES maquinas(id),
    FOREIGN KEY (operario_id) REFERENCES usuarios(id) ON DELETE SET NULL,
    FOREIGN KEY (herramienta_id) REFERENCES herramientas(id) ON DELETE SET NULL
);

-- 7. KPIs consolidados por turno de trabajo
CREATE TABLE IF NOT EXISTS kpi_turnos (
    id INT AUTO_INCREMENT PRIMARY KEY,
    maquina_id INT NOT NULL,
    fecha DATE NOT NULL,
    turno ENUM('MAÑANA', 'TARDE', 'NOCHE') NOT NULL,
    tiempo_activo_seg INT DEFAULT 0,
    tiempo_inactivo_seg INT DEFAULT 0,
    porcentaje_disponibilidad DECIMAL(5,2) DEFAULT 0.00,
    cantidad_paradas INT DEFAULT 0,
    FOREIGN KEY (maquina_id) REFERENCES maquinas(id) ON DELETE CASCADE,
    UNIQUE KEY uk_maquina_turno (maquina_id, fecha, turno)
);

-- 8. Configuración Global del Sistema
CREATE TABLE IF NOT EXISTS configuracion_sistema (
    clave VARCHAR(50) PRIMARY KEY,
    valor VARCHAR(255) NOT NULL,
    descripcion VARCHAR(255) NULL
);

INSERT INTO configuracion_sistema (clave, valor, descripcion) VALUES
('timeout_inactividad_minutos', '10', 'Tiempo de inactividad (minutos) para cerrar actividad automaticamente'),
('turno_manana_inicio', '07:00', 'Hora inicio turno mañana'),
('turno_manana_fin', '12:00', 'Hora fin turno mañana'),
('turno_tarde_inicio', '14:00', 'Hora inicio turno tarde'),
('turno_tarde_fin', '17:00', 'Hora fin turno tarde'),
('turno_noche_inicio', '22:00', 'Hora inicio turno noche'),
('turno_noche_fin', '06:00', 'Hora fin turno noche')
ON DUPLICATE KEY UPDATE valor=VALUES(valor);
