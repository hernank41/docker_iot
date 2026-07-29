CREATE DATABASE IF NOT EXISTS metalurgica_db;
USE metalurgica_db;

-- Tabla de máquinas monitoreadas
CREATE TABLE IF NOT EXISTS maquinas (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nombre VARCHAR(50) NOT NULL UNIQUE,
    tipo VARCHAR(50) NOT NULL,
    ubicacion VARCHAR(100) DEFAULT 'Planta Principal'
);

-- Carga inicial de máquinas industriales (Torno y Fresadora)
INSERT INTO maquinas (nombre, tipo) VALUES 
('Torno_Pinacho', 'Torno'),
('Fresadora_Universal', 'Fresadora')
ON DUPLICATE KEY UPDATE nombre=nombre;

-- Registro de cambios de estado en tiempo real (Telemetría de contactores)
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

-- KPIs consolidados por turno de trabajo
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
