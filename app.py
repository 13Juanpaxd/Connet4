from flask import json
from flask import Flask, render_template, request, redirect, url_for, send_from_directory, jsonify
import oracledb
import os

app = Flask(__name__)
app.secret_key = 'mi_clave_secreta'

##ESTO PARA EL LOGO Y ASSETS
@app.route('/Assets/<path:filename>')
def serve_assets(filename):
    assets_dir = os.path.join(app.root_path, 'Assets')
    if not os.path.exists(assets_dir):
        os.makedirs(assets_dir) 
    return send_from_directory(assets_dir, filename)

def get_db_connection():
    try:
        return oracledb.connect(
            user='KUATRO',
            password='KUATRO',
            dsn='localhost:1521/xe'
        )
    except oracledb.DatabaseError as e:
        print(f"Error de conexión: {e}")
        return None

#################################################################
#############################RUTAS###############################
#################################################################
# Menú principal
@app.route('/')
def menu():
    return render_template('menu.html')

# Registro de jugadores
@app.route('/registro', methods=['POST'])
def registro():
    if request.method == 'POST':
        nombre = request.form.get('nombre', '').strip()
        identificacion = request.form.get('identificacion', '').strip()
        
        if not nombre or not identificacion:
            return jsonify({'success': False, 'message': 'Debe ingresar nombre e identificación'})
        
        conn = get_db_connection()
        if conn:
            try:
                cursor = conn.cursor()
                # Verificar si ya existe
                cursor.execute("""
                    SELECT COUNT(*) FROM Jugadores 
                    WHERE LOWER(Nombre) = LOWER(:nombre) OR Identificacion = :identificacion
                """, {'nombre': nombre, 'identificacion': identificacion})
                
                if cursor.fetchone()[0] > 0:
                    return jsonify({'success': False, 'message': 'El nombre o identificación ya existen'})
                
                # Insertar nuevo jugador
                cursor.execute(
                    "INSERT INTO Jugadores (Nombre, Identificacion, Puntuacion, Ganadas, Empatadas, Perdidas) "
                    "VALUES (:nombre, :identificacion, 0, 0, 0, 0)",
                    {'nombre': nombre, 'identificacion': identificacion}
                )
                conn.commit()
                return jsonify({'success': True, 'message': f'¡{nombre} registrado con éxito!'})
                
            except Exception as e:
                return jsonify({'success': False, 'message': f'Error: {str(e)}'})
            finally:
                cursor.close()
                conn.close()
        
        return jsonify({'success': False, 'message': 'Error de conexión a la base de datos'})


#################################################################
# Utilidad para obtener datos de partida y stats
def obtener_datos_partida(id_partida):
    jugador1 = jugador2 = partida_json = estado = None
    conn = get_db_connection()
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT j1.Nombre, j2.Nombre, p.Partida, p.Estado
                FROM Partidas p
                JOIN Jugadores j1 ON p.IDJUGADOR = j1.JugadorID
                JOIN Jugadores j2 ON p.IDRival = j2.JugadorID
                WHERE p.PartidaID = :pid
            ''', {'pid': id_partida})
            row = cursor.fetchone()
            if row:
                jugador1, jugador2, partida_json, estado = row[0], row[1], row[2], row[3]
                # Asegurar que los valores null/None sean consistentes
                if partida_json:
                    partida_data = json.loads(partida_json)
                    if 'tablero' in partida_data:
                        # Convertir cualquier valor que no sea 0 o 1 a None
                        partida_data['tablero'] = [
                            [cell if cell in [0, 1] else None for cell in row]
                            for row in partida_data['tablero']
                        ]
                    partida_json = json.dumps(partida_data)
        except Exception as e:
            print(f"Error al cargar partida: {e}")
        finally:
            conn.close()
    def get_stats(nombre):
        conn = get_db_connection()
        if conn:
            try:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT Puntuacion, Ganadas, Empatadas, Perdidas FROM Jugadores WHERE Nombre = :nombre",
                    {'nombre': nombre}
                )
                result = cursor.fetchone()
                if result:
                    return {
                        'Puntuacion': result[0],
                        'Ganadas': result[1],
                        'Empatadas': result[2],
                        'Perdidas': result[3]
                    }
            except Exception as e:
                print(f"Error al obtener estadísticas: {e}")
            finally:
                conn.close()
        return None
    stats1 = get_stats(jugador1)
    stats2 = get_stats(jugador2)
    return jugador1, jugador2, partida_json, estado, stats1, stats2

@app.route('/juego')
def juego():
    id_partida = request.args.get('id_partida')
    jugador1 = request.args.get('jugador1')
    jugador2 = request.args.get('jugador2')
    
    # Validación básica de parámetros
    if not jugador1 or not jugador2:
        return jsonify({
            'success': False,
            'error': 'Parámetros requeridos: jugador1 y jugador2'
        }), 400
    
    # Si no hay ID de partida, crear una nueva
    if not id_partida:
        try:
            # Crear nueva partida directamente sin redirección intermedia
            conn = get_db_connection()
            if not conn:
                return jsonify({
                    'success': False,
                    'error': 'Error de conexión a la base de datos'
                }), 500
                
            cursor = conn.cursor()
            
            # Obtener IDs de los jugadores
            cursor.execute("SELECT JugadorID FROM Jugadores WHERE Nombre = :nombre", {'nombre': jugador1})
            id_jugador = cursor.fetchone()
            cursor.execute("SELECT JugadorID FROM Jugadores WHERE Nombre = :nombre", {'nombre': jugador2})
            id_rival = cursor.fetchone()
            
            if not id_jugador or not id_rival:
                return jsonify({
                    'success': False,
                    'error': 'Uno o ambos jugadores no existen'
                }), 400

            # Crear nueva partida
            nueva_partida = {
                'tablero': [[None]*7 for _ in range(6)],
                'turno': 0
            }
            
            cursor.execute(
                """
                INSERT INTO Partidas (IDJUGADOR, IDRival, Estado, Partida)
                VALUES (:idj, :idr, 'En progreso', :partida)
                """,
                {
                    'idj': id_jugador[0],
                    'idr': id_rival[0],
                    'partida': json.dumps(nueva_partida)
                }
            )
            
            # Obtener el ID de la nueva partida
            cursor.execute("""
                SELECT PartidaID FROM Partidas 
                WHERE ROWID = (SELECT MAX(ROWID) FROM Partidas)
                """)
            nueva_partida_id = cursor.fetchone()[0]
            
            conn.commit()
            
            # Redirigir a la vista del juego con el nuevo ID
            return redirect(url_for('juego', 
                                 id_partida=nueva_partida_id,
                                 jugador1=jugador1,
                                 jugador2=jugador2))
            
        except Exception as e:
            if conn:
                conn.rollback()
            return jsonify({
                'success': False,
                'error': f'Error al crear partida: {str(e)}'
            }), 500
        finally:
            if conn:
                conn.close()
    
    # Cargar partida existente
    try:
        jugador1, jugador2, partida_json, estado, stats1, stats2 = obtener_datos_partida(id_partida)
        
        if not partida_json:
            return jsonify({
                'success': False,
                'error': 'Partida no encontrada'
            }), 404
            
        if estado == 'Terminada':
            return redirect(url_for('ver_partida', id_partida=id_partida))
            
        return render_template('conecta4.html', 
                            jugador1=jugador1, 
                            jugador2=jugador2,
                            stats1=stats1,
                            stats2=stats2,
                            partida_json=partida_json)
                            
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Error al cargar partida: {str(e)}'
        }), 500

@app.route('/ver_partida')
def ver_partida():
    id_partida = request.args.get('id_partida')
    if not id_partida:
        return "ID de partida requerido", 400
    jugador1, jugador2, partida_json, estado, stats1, stats2 = obtener_datos_partida(id_partida)
    return render_template('conecta4_ver.html', 
                         jugador1=jugador1, 
                         jugador2=jugador2,
                         stats1=stats1,
                         stats2=stats2,
                         partida_json=partida_json,
                         estado=estado)

#################################################################
@app.route('/actualizar_estadisticas', methods=['POST'])
def actualizar_estadisticas():
    data = request.json
    ganador = data.get('ganador')
    perdedor = data.get('perdedor')
    
    conn = get_db_connection()
    if conn:
        try:
            cursor = conn.cursor()
            
            # Actualizar estadísticas del ganador
            cursor.execute("""
                UPDATE Jugadores 
                SET 
                    Puntuacion = Puntuacion + 1,
                    Ganadas = Ganadas + 1
                WHERE Nombre = :nombre
            """, {'nombre': ganador})
            
            # Actualizar estadísticas del perdedor
            cursor.execute("""
                UPDATE Jugadores 
                SET 
                    Puntuacion = Puntuacion - 1,
                    Perdidas = Perdidas + 1
                WHERE Nombre = :nombre
            """, {'nombre': perdedor})
            
            conn.commit()
            return jsonify({'success': True})
            
        except Exception as e:
            print(f"Error al actualizar estadísticas: {e}")
            conn.rollback()
            return jsonify({'success': False, 'error': str(e)}), 500
            
        finally:
            conn.close()
    
    return jsonify({'success': False, 'error': 'No se pudo conectar a la base de datos'}), 500
#################################################################
@app.route('/actualizar_empate', methods=['POST'])
def actualizar_empate():
    data = request.json
    jugador1 = data.get('jugador1')
    jugador2 = data.get('jugador2')
    
    conn = get_db_connection()
    if conn:
        try:
            cursor = conn.cursor()
            
            # Actualizar estadísticas para ambos jugadores
            cursor.execute("""
                UPDATE Jugadores 
                SET 
                    Empatadas = Empatadas + 1
                WHERE Nombre = :nombre
            """, {'nombre': jugador1})
            
            cursor.execute("""
                UPDATE Jugadores 
                SET 
                    Empatadas = Empatadas + 1
                WHERE Nombre = :nombre
            """, {'nombre': jugador2})
            
            conn.commit()
            return jsonify({'success': True})
            
        except Exception as e:
            print(f"Error al actualizar empate: {e}")
            conn.rollback()
            return jsonify({'success': False, 'error': str(e)}), 500
            
        finally:
            conn.close()
    
    return jsonify({'success': False, 'error': 'No se pudo conectar a la base de datos'}), 500

#################################################################
@app.route('/api/escalafon')
def api_escalafon():
    conn = get_db_connection()
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT Identificacion, Nombre, Puntuacion, Ganadas, Empatadas, Perdidas 
                FROM Jugadores 
                ORDER BY Puntuacion DESC, Nombre ASC
            """)
            jugadores = [
                {
                    'Identificacion': row[0],
                    'Nombre': row[1],
                    'Puntuacion': row[2],
                    'Ganadas': row[3],
                    'Empatadas': row[4],
                    'Perdidas': row[5]
                } for row in cursor.fetchall()
            ]
            return jsonify(jugadores)
        except Exception as e:
            return jsonify({'error': str(e)}), 500
        finally:
            cursor.close()
            conn.close()
    return jsonify({'error': 'No se pudo conectar a la base de datos'}), 500
#################################################################
@app.route('/api/crear_partida', methods=['POST'])
def api_crear_partida():
    data = request.json
    jugador1 = data.get('jugador1')
    jugador2 = data.get('jugador2')
    estado = 'En progreso'
    partida = data.get('partida', None) or {'tablero': [[None]*7 for _ in range(6)], 'turno': 0}

    conn = get_db_connection()
    if conn:
        try:
            cursor = conn.cursor()
            
            # Obtener IDs de los jugadores
            cursor.execute("SELECT JugadorID FROM Jugadores WHERE Nombre = :nombre", {'nombre': jugador1})
            id_jugador = cursor.fetchone()
            cursor.execute("SELECT JugadorID FROM Jugadores WHERE Nombre = :nombre", {'nombre': jugador2})
            id_rival = cursor.fetchone()
            
            if not id_jugador or not id_rival:
                return jsonify({'error': 'Jugador no encontrado'}), 400

            # Insertar partida
            cursor.execute(
                """
                INSERT INTO Partidas (IDJUGADOR, IDRival, Estado, Partida)
                VALUES (:idj, :idr, :estado, :partida)
                """,
                {
                    'idj': id_jugador[0],
                    'idr': id_rival[0],
                    'estado': estado,
                    'partida': json.dumps(partida)
                }
            )
            
            # Obtener el ID de la nueva partida
            cursor.execute("""
                SELECT PartidaID FROM Partidas 
                WHERE ROWID = (SELECT MAX(ROWID) FROM Partidas)
                """)
            partida_id = cursor.fetchone()[0]
            
            conn.commit()
            return jsonify({
                'success': True,
                'id_partida': partida_id
            })
            
        except Exception as e:
            conn.rollback()
            return jsonify({'error': str(e)}), 500
        finally:
            cursor.close()
            conn.close()
    return jsonify({'error': 'No se pudo conectar a la base de datos'}), 500

#################################################################
@app.route('/api/terminar_partida', methods=['POST'])
def api_terminar_partida():
    data = request.json
    jugador1 = data.get('jugador1')
    jugador2 = data.get('jugador2')
    conn = get_db_connection()
    if conn:
        try:
            cursor = conn.cursor()
            # Buscar la última partida en progreso entre estos jugadores
            cursor.execute('''
                SELECT PartidaID FROM Partidas
                WHERE Estado = 'En progreso'
                  AND ((IDJUGADOR = (SELECT JugadorID FROM Jugadores WHERE Nombre = :j1) AND IDRival = (SELECT JugadorID FROM Jugadores WHERE Nombre = :j2))
                    OR (IDJUGADOR = (SELECT JugadorID FROM Jugadores WHERE Nombre = :j2) AND IDRival = (SELECT JugadorID FROM Jugadores WHERE Nombre = :j1)))
                ORDER BY FechaCreacion DESC FETCH FIRST 1 ROWS ONLY
            ''', {'j1': jugador1, 'j2': jugador2})
            row = cursor.fetchone()
            if row:
                partida_id = row[0]
                cursor.execute("UPDATE Partidas SET Estado = 'Terminada' WHERE PartidaID = :pid", {'pid': partida_id})
                conn.commit()
                return jsonify({'success': True})
            else:
                return jsonify({'error': 'No se encontró partida en progreso'}), 404
        except Exception as e:
            conn.rollback()
            return jsonify({'error': str(e)}), 500
        finally:
            cursor.close()
            conn.close()
    return jsonify({'error': 'No se pudo conectar a la base de datos'}), 500

#################################################################
@app.route('/api/actualizar_partida', methods=['POST'])
def api_actualizar_partida():
    data = request.json
    jugador1 = data.get('jugador1')
    jugador2 = data.get('jugador2')
    partida = data.get('partida')
    conn = get_db_connection()
    if conn:
        try:
            cursor = conn.cursor()
            # Buscar la última partida en progreso entre estos jugadores
            cursor.execute('''
                SELECT PartidaID FROM Partidas
                WHERE Estado = 'En progreso'
                  AND ((IDJUGADOR = (SELECT JugadorID FROM Jugadores WHERE Nombre = :j1) AND IDRival = (SELECT JugadorID FROM Jugadores WHERE Nombre = :j2))
                    OR (IDJUGADOR = (SELECT JugadorID FROM Jugadores WHERE Nombre = :j2) AND IDRival = (SELECT JugadorID FROM Jugadores WHERE Nombre = :j1)))
                ORDER BY FechaCreacion DESC FETCH FIRST 1 ROWS ONLY
            ''', {'j1': jugador1, 'j2': jugador2})
            row = cursor.fetchone()
            if row:
                partida_id = row[0]
                cursor.execute("UPDATE Partidas SET Partida = :partida WHERE PartidaID = :pid", {'partida': json.dumps(partida), 'pid': partida_id})
                conn.commit()
                return jsonify({'success': True})
            else:
                return jsonify({'error': 'No se encontró partida en progreso'}), 404
        except Exception as e:
            conn.rollback()
            return jsonify({'error': str(e)}), 500
        finally:
            cursor.close()
            conn.close()
    return jsonify({'error': 'No se pudo conectar a la base de datos'}), 500
##################################################################
# API para listar partidas
@app.route('/api/listar_partidas')
def api_listar_partidas():
    conn = get_db_connection()
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT p.PartidaID, j1.Nombre, j2.Nombre, p.Estado, TO_CHAR(p.FechaCreacion, 'YYYY-MM-DD HH24:MI:SS')
                FROM Partidas p
                JOIN Jugadores j1 ON p.IDJUGADOR = j1.JugadorID
                JOIN Jugadores j2 ON p.IDRival = j2.JugadorID
                ORDER BY p.FechaCreacion DESC
            ''')
            partidas = [
                {
                    'PartidaID': row[0],
                    'Jugador1': row[1],
                    'Jugador2': row[2],
                    'Estado': row[3],
                    'Fecha': row[4]
                } for row in cursor.fetchall()
            ]
            return jsonify(partidas)
        except Exception as e:
            return jsonify({'error': str(e)}), 500
        finally:
            cursor.close()
            conn.close()
    return jsonify({'error': 'No se pudo conectar a la base de datos'}), 500
##################################################################
# Nueva ruta para actualizar partida por ID
@app.route('/api/actualizar_partida_por_id', methods=['POST'])
def api_actualizar_partida_por_id():
    data = request.json
    partida_id = data.get('id_partida')
    partida = data.get('partida')
    
    conn = get_db_connection()
    if conn:
        try:
            cursor = conn.cursor()
            # Verificar si la partida existe y está en progreso
            cursor.execute("""
                SELECT Estado FROM Partidas WHERE PartidaID = :pid
            """, {'pid': partida_id})
            row = cursor.fetchone()
            
            if not row:
                return jsonify({'error': 'Partida no encontrada'}), 404
                
            if row[0] != 'En progreso':
                return jsonify({'error': 'La partida no está en progreso'}), 400
                
            # Actualizar la partida
            cursor.execute("""
                UPDATE Partidas 
                SET Partida = :partida 
                WHERE PartidaID = :pid
            """, {'partida': json.dumps(partida), 'pid': partida_id})
            
            conn.commit()
            return jsonify({'success': True})
            
        except Exception as e:
            conn.rollback()
            return jsonify({'error': str(e)}), 500
        finally:
            conn.close()
    return jsonify({'error': 'No se pudo conectar a la base de datos'}), 500
##################################################################

@app.route('/api/crear_nueva_partida', methods=['POST'])
def api_crear_nueva_partida():
    data = request.json
    jugador1 = data.get('jugador1')
    jugador2 = data.get('jugador2')
    id_partida_original = data.get('id_partida_original')

    # Configuración inicial de nueva partida
    nueva_partida = {
        'tablero': [[None]*7 for _ in range(6)],
        'turno': 0
    }

    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'No se pudo conectar a la base de datos'}), 500

    try:
        cursor = conn.cursor()

        # Obtener IDs de los jugadores
        cursor.execute("SELECT JugadorID FROM Jugadores WHERE Nombre = :nombre", {'nombre': jugador1})
        id_jugador = cursor.fetchone()
        cursor.execute("SELECT JugadorID FROM Jugadores WHERE Nombre = :nombre", {'nombre': jugador2})
        id_rival = cursor.fetchone()

        if not id_jugador or not id_rival:
            return jsonify({'error': 'Uno de los jugadores no existe'}), 404

        # Para Oracle necesitamos usar una secuencia
        # Primero insertamos
        cursor.execute("""
            INSERT INTO Partidas (IDJUGADOR, IDRival, Estado, Partida)
            VALUES (:idj, :idr, 'En progreso', :partida)
            """,
            {
                'idj': id_jugador[0],
                'idr': id_rival[0],
                'partida': json.dumps(nueva_partida)
            }
        )
        
        # Luego obtenemos el ID recién insertado
        cursor.execute("""
            SELECT PartidaID FROM Partidas 
            WHERE ROWID = (SELECT MAX(ROWID) FROM Partidas)
            """)
        nueva_partida_id = cursor.fetchone()[0]
        
        conn.commit()

        return jsonify({
            'success': True,
            'id_partida': nueva_partida_id
        })

    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        if conn:
            conn.close()

##################################################################
@app.route('/api/terminar_partida_por_id', methods=['POST'])
def api_terminar_partida_por_id():
    data = request.json
    partida_id = data.get('id_partida')
    
    conn = get_db_connection()
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE Partidas 
                SET Estado = 'Terminada' 
                WHERE PartidaID = :pid
            """, {'pid': partida_id})
            
            conn.commit()
            return jsonify({'success': True})
            
        except Exception as e:
            conn.rollback()
            return jsonify({'error': str(e)}), 500
        finally:
            conn.close()
    return jsonify({'error': 'No se pudo conectar a la base de datos'}), 500
##################################################################
@app.route('/api/crear_partida_front')
def api_crear_partida_front():
    jugador1 = request.args.get('jugador1')
    jugador2 = request.args.get('jugador2')
    
    if not jugador1 or not jugador2:
        return "Parámetros requeridos: jugador1 y jugador2", 400
    
    try:
        # Crear nueva partida
        response = requests.post(
            'http://localhost:5000/api/crear_partida',
            json={'jugador1': jugador1, 'jugador2': jugador2},
            headers={'Content-Type': 'application/json'}
        )
        
        if response.status_code != 200:
            return "Error al crear partida", 500
            
        data = response.json()
        return redirect(url_for('juego',
                              id_partida=data['id_partida'],
                              jugador1=jugador1,
                              jugador2=jugador2))
    except Exception as e:
        return f"Error: {str(e)}", 500
##################################################################

if __name__ == '__main__':
    app.run(debug=True)