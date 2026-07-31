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

-- Carga inicial de herramientas
INSERT INTO herramientas (maquina_id, nombre, horas_uso, horas_expectativa) VALUES
(1, 'Cuchilla WNMG 080408 (Torno 1)', 38.50, 60.00),
(1, 'Inserto Tronzador 3mm (Torno 1)', 12.00, 30.00),
(2, 'Fresa Frontal Ø20mm (Fresadora 1)', 42.00, 50.00),
(2, 'Fresa Planeadora Ø50mm (Fresadora 1)', 18.00, 80.00)
ON DUPLICATE KEY UPDATE nombre=nombre;

-- 4. Tabla de Asignación Actual de Máquinas
CREATE TABLE IF NOT EXISTS asignaciones_actuales (
    maquina_id INT PRIMARY KEY,
    operario_id INT NULL,
    herramienta_id INT NULL,
    FOREIGN KEY (maquina_id) REFERENCES maquinas(id),
    FOREIGN KEY (operario_id) REFERENCES usuarios(id) ON DELETE SET NULL,
    FOREIGN KEY (herramienta_id) REFERENCES herramientas(id) ON DELETE SET NULL
);

INSERT INTO asignaciones_actuales (maquina_id, operario_id, herramienta_id) VALUES
(1, 2, 1),
(2, 3, 3)
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

-- 9. Datos Semilla de Actividades (Lunes a Jueves - Turnos Mañana 07-12h y Tarde 14-17h)
-- Lunes 2026-07-27 (Turno Mañana: Juan Perez en Torno 1, Turno Tarde: Carlos Gomez en Fresadora 1)
INSERT INTO actividades (maquina_id, operario_id, herramienta_id, fecha_inicio, fecha_fin, tiempo_activo_segundos, estado, comentario) VALUES
(1, 2, 1, '2026-07-27 07:15:00', '2026-07-27 08:45:00', 5150, 'FINALIZADA', 'Mecanizado de ejes de acero 1045'),
(1, 2, 1, '2026-07-27 09:30:00', '2026-07-27 11:20:00', 6300, 'FINALIZADA', 'Roscado y desbaste exterior batch A'),
(2, 3, 3, '2026-07-27 14:10:00', '2026-07-27 16:00:00', 6100, 'FINALIZADA', 'Planeado de placas base de lubricación');

-- Martes 2026-07-28 (Turno Mañana: Carlos Gomez en Fresadora 1, Turno Tarde vacio en Torno 1)
INSERT INTO actividades (maquina_id, operario_id, herramienta_id, fecha_inicio, fecha_fin, tiempo_activo_segundos, estado, comentario) VALUES
(2, 3, 3, '2026-07-28 07:30:00', '2026-07-28 09:10:00', 5700, 'FINALIZADA', 'Ranurado de chaveteros de precisión'),
(2, 3, 4, '2026-07-28 10:00:00', '2026-07-28 11:45:00', 5850, 'FINALIZADA', 'Fresado perimetral de soportes rectificados');

-- Miércoles 2026-07-29 (Turno Mañana: Juan Perez en Torno 1, Turno Tarde: Juan Perez en Torno 1)
INSERT INTO actividades (maquina_id, operario_id, herramienta_id, fecha_inicio, fecha_fin, tiempo_activo_segundos, estado, comentario) VALUES
(1, 2, 1, '2026-07-29 07:05:00', '2026-07-29 08:35:00', 5100, 'FINALIZADA', 'Cilindrado de bujes de bronce'),
(1, 2, 2, '2026-07-29 09:00:00', '2026-07-29 10:40:00', 5600, 'FINALIZADA', 'Tronzado de piezas de serie 200'),
(1, 2, 1, '2026-07-29 14:15:00', '2026-07-29 15:50:00', 5200, 'FINALIZADA', 'Rectificado y pulido final de ejes');

-- Jueves 2026-07-30 (Turno Mañana: Carlos Gomez en Fresadora 1)
INSERT INTO actividades (maquina_id, operario_id, herramienta_id, fecha_inicio, fecha_fin, tiempo_activo_segundos, estado, comentario) VALUES
(2, 3, 3, '2026-07-30 07:45:00', '2026-07-30 09:30:00', 5900, 'FINALIZADA', 'Taladrado y mandrinado de carcasa de engranajes'),
(2, 3, 3, '2026-07-30 10:15:00', '2026-07-30 11:50:00', 5400, 'FINALIZADA', 'Control dimensional y biselado de bordes');
