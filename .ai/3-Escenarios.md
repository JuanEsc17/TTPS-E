**Escenarios – Técnica de Julio César Sampaio do Prado Leite**

Basado en la entrevista proporcionada para el ejercicio de TTPS.

## **Escenario 1: Dar de alta un paciente**

**Objetivo:** Registrar un paciente con sus datos clínicos y familiares para iniciar un estudio.

**Contexto:** El paciente es atendido por un médico y necesita ser incorporado al sistema para realizar un estudio de exoma clínico.

**Actores:** Paciente; Médico tratante.

**Recursos:** DNI, datos personales, diagnóstico presuntivo, historia clínica, síntomas SNOMED, datos familiares y familiograma.

**Episodios:**

1. El médico selecciona al paciente.  
2. El médico registra los datos personales del paciente.  
3. El médico registra el diagnóstico presuntivo.  
4. El médico registra los síntomas del paciente.  
5. El sistema valida la correspondencia entre diagnóstico presuntivo y síntomas.  
6. El sistema registra al paciente cuando la validación es correcta.

## **Escenario 2: Dar de alta un estudio**

**Objetivo:** Registrar un estudio de exoma clínico asociado a un paciente.

**Contexto:** El paciente está registrado y el médico solicita un estudio de exoma clínico.

**Actores:** Médico tratante; Paciente.

**Recursos:** Datos del paciente, lista de genes, sospecha de patología, hallazgos secundarios.

**Episodios:**

1. El médico selecciona al paciente.  
2. El médico selecciona la lista de genes.  
3. El sistema obtiene la lista de genes relacionada con la patología sospechada.  
4. El médico agrega genes adicionales cuando corresponde.  
5. El sistema registra el estudio.

## **Escenario 3: Emitir un presupuesto**

**Objetivo:** Determinar el costo del estudio solicitado y registrar el presupuesto.

**Contexto:** El médico creó un estudio de exoma clínico y el laboratorio debe determinar su costo.

**Actores:** Personal administrativo.

**Recursos:** Estudio, cantidad de genes, presupuesto.

**Episodios:**

1. El personal administrativo consulta la cantidad de genes del estudio.  
2. El sistema calcula el precio de hasta cinco genes.  
3. El sistema agrega el costo correspondiente a los genes adicionales.  
4. El sistema registra el presupuesto.

## **Escenario 4: Autorizar un estudio por obra social**

**Objetivo:** Registrar la autorización de un estudio financiado por una obra social.

**Contexto:** El presupuesto está emitido y el paciente utiliza una obra social.

**Actores:** Personal administrativo.

**Recursos:** Presupuesto, datos de cobertura, autorización de la obra social.

**Episodios:**

1. El personal administrativo gestiona la autorización de la obra social.  
2. El personal administrativo registra el resultado de la autorización.  
3. El sistema registra el estudio como autorizado cuando la obra social lo aprueba.  
4. El sistema registra el pago asociado a la autorización.

## **Escenario 5: Reautorizar un estudio rechazado**

**Objetivo:** Solicitar nuevamente la autorización de un estudio rechazado por la obra social.

**Contexto:** La obra social rechazó la autorización inicial del estudio.

**Actores:** Paciente; Personal administrativo.

**Recursos:** Documento PDF de la decisión judicial, solicitud de reautorización.

**Episodios:**

1. El paciente carga la decisión judicial favorable.  
2. El personal administrativo solicita la reautorización.  
3. El personal administrativo registra la nueva autorización.  
4. El estudio continúa su proceso.

## **Escenario 6: Pagar un estudio particular**

**Objetivo:** Registrar el pago particular de un estudio.

**Contexto:** El paciente realiza el estudio de forma particular.

**Actores:** Paciente.

**Recursos:** Presupuesto, registro financiero, medio de pago simulado.

**Episodios:**

1. El paciente selecciona el pago particular.  
2. El paciente completa el pago simulado.  
3. El sistema registra el movimiento financiero.  
4. El estudio queda habilitado para continuar.

 

## **Escenario 7: Solicitar un turno de extracción**

**Objetivo:** Asignar un turno para realizar la extracción de sangre.

**Contexto:** El estudio está autorizado o pagado y el paciente debe realizar la extracción.

**Actores:** Paciente.

**Recursos:** Centros de extracción, mapa, agenda, turno.

**Episodios:**

1. El paciente consulta los centros de extracción disponibles.  
2. El sistema muestra los centros y sus turnos disponibles.  
3. El paciente selecciona un centro.  
4. El paciente selecciona un turno.  
5. El sistema registra el turno de extracción.

## **Escenario 8: Cancelar un turno de extracción**

**Objetivo:** Cancelar un turno de extracción previamente asignado.

**Contexto:** El paciente tiene un turno de extracción registrado.

**Actores:** Paciente.

**Recursos:** Turno de extracción.

**Episodios:**

1. El paciente solicita cancelar el turno.  
2. El sistema registra la cancelación.  
3. El paciente puede solicitar un nuevo turno.

## **Escenario 9: Registrar la toma de una muestra**

**Objetivo:** Registrar que una muestra fue obtenida en un centro de extracción.

**Contexto:** El paciente concurrió al centro de extracción y se obtuvo la muestra.

**Actores:** Centro de extracción; Personal administrativo.

**Recursos:** Muestra de sangre, mensaje de confirmación, estado del estudio.

**Episodios:**

1. El Centro de extracción informa la toma de la muestra.  
2. El sistema recibe el aviso.  
3. El sistema cambia el estado de la muestra.  
4. El sistema informa que la muestra está lista para ser retirada.

## **Escenario 10: Remuestrear un estudio**

**Objetivo:** Obtener una nueva muestra cuando la muestra original no puede ser procesada.

**Contexto:** La muestra presenta ADN insuficiente o se encuentra desnaturalizada por una mala conservación.

**Actores:** Paciente; Médico tratante; Personal administrativo.

**Recursos:** Muestra, turno de extracción, estudio.

**Episodios:**

1. El laboratorio detecta que la muestra no puede ser procesada.  
2. El paciente recibe la notificación de la necesidad de una nueva muestra.  
3. El médico recibe la notificación correspondiente.  
4. El paciente solicita un nuevo turno.  
5. El paciente realiza una nueva extracción.

## **Escenario 11: Transportar muestras al laboratorio central**

**Objetivo:** Trasladar las muestras desde los centros de extracción hasta el laboratorio central.

**Contexto:** Existen muestras listas para ser retiradas en los centros de extracción.

**Actores:** Transportista.

**Recursos:** Orden de recorrido, muestras, estados de transporte.

**Episodios:**

1. El transportista recibe la lista diaria de centros.  
2. El transportista retira las muestras de cada centro.  
3. El sistema registra la muestra como en transporte.  
4. El transportista informa la llegada de las muestras al laboratorio central.  
5. El sistema actualiza el estado de las muestras.

## **Escenario 12: Formar un sample-set de muestras**

**Objetivo:** Agrupar las muestras recibidas en conjuntos de diez para su envío.

**Contexto:** Las muestras llegaron al laboratorio central.

**Actores:** 

**Recursos:** Muestras, sample-set de muestras.

**Episodios:**

1. El sistema recibe las muestras del laboratorio central.  
2. El sistema agrupa las muestras en conjuntos de diez.  
3. El sistema crea el sample-set correspondiente.  
4. El sistema mantiene el sample-set sin modificar una vez iniciado el siguiente estado.

## **Escenario 13: Enviar un sample-set de muestras a Corea**

**Objetivo:** Gestionar el envío de un sample-set autorizado al laboratorio de Corea.

**Contexto:** El sample-set está formado y requiere autorización del Ministerio de Salud.

**Actores:** Personal administrativo.

**Recursos:** Sample-set, archivo CSV, autorización del Ministerio, paquete, datos de FedEx.

**Episodios:**

1. El sistema genera el archivo CSV con los pacientes del sample-set.  
2. El sistema envía el CSV al Ministerio de Salud.  
3. El sistema recibe el PDF de autorización.  
4. El personal administrativo programa el retiro de FedEx.  
5. FedEx retira el paquete en el horario programado.  
6. El sistema cambia el estado del sample-set y de las muestras a en tránsito a Corea.

## **Escenario 14: Enviar una muestra de Pompe urgente**

**Objetivo:** Enviar un conjunto de muestras sin esperar a completar diez cuando corresponde a un caso urgente de Pompe.

**Contexto:** Un paciente con Pompe tiene menos de cuatro meses de edad.

**Actores:** Personal administrativo; Transportista.

**Recursos:** Muestras, sample-set parcial, autorización, paquete.

**Episodios:**

1. El sistema identifica el caso urgente de Pompe.  
2. El personal administrativo prepara el envío urgente.  
3. El sistema incluye el sample-set parcial en el envío.  
4. El transportista retira el paquete.  
5. El sistema cambia el estado de las muestras a en tránsito a Corea.

## **Escenario 15: Analizar un estudio mediante bioinformática**

**Objetivo:** Registrar las variantes encontradas en el análisis bioinformático de un estudio.

**Contexto:** Los datos provenientes de Corea están disponibles para su análisis.

**Actores:** Bioinformático.

**Recursos:** Datos genéticos, estudio, genes, variantes, clasificación de variantes.

**Episodios:**

1. El sistema recibe los datos crudos provenientes de Corea.  
2. El bioinformático selecciona los genes a analizar.  
3. El sistema consulta las variantes conocidas.  
4. El bioinformático registra las variantes encontradas.  
5. El sistema registra la clasificación de las variantes.

## **Escenario 16: Informar el resultado de un estudio**

**Objetivo:** Comunicar al paciente y al médico el resultado del estudio.

**Contexto:** El análisis bioinformático finalizó.

**Actores:** Paciente; Médico tratante.

**Recursos:** Resultado del exoma, variante genética, PDF del resultado, notificaciones.

**Episodios:**

1. El sistema registra el resultado del estudio.  
2. El sistema genera el resultado en formato PDF.  
3. El sistema notifica al paciente.  
4. El sistema notifica al médico tratante.  
5. El paciente puede descargar el resultado.

## **Escenario 17: Reanalizar un estudio**

**Objetivo:** Analizar nuevos genes utilizando el mismo exoma previamente obtenido.

**Contexto:** Existe una nueva sospecha clínica o un gen que no fue considerado en el análisis inicial.

**Actores:** Médico tratante; Bioinformático; Paciente.

**Recursos:** Exoma existente, nuevos genes, historial de estudios.

**Episodios:**

1. El médico solicita una reanálisis del estudio.  
2. El médico indica los nuevos genes a analizar.  
3. El bioinformático analiza los datos existentes.  
4. El sistema registra el nuevo análisis en el historial del paciente.

## **Escenario 18: Gestionar la información familiar**

**Objetivo:** Registrar información de familiares vinculada al paciente cuando existe.

**Contexto:** El paciente tiene información familiar relevante para el estudio.

**Actores:** Médico tratante; Paciente.

**Recursos:** Datos de familiares, relación, síntomas, diagnóstico, familiograma.

**Episodios:**

1. El médico registra los familiares del paciente.  
2. El médico registra la relación con cada familiar.  
3. El médico registra los síntomas de los familiares.  
4. El sistema asocia el familiograma al paciente.

## **Escenario 19: Registrar un paciente sin información familiar**

**Objetivo:** Continuar el registro de un paciente cuando no existen datos familiares.

**Contexto:** El paciente no dispone de información familiar para registrar.

**Actores:** Médico tratante; Paciente.

**Recursos:** Datos personales, datos clínicos.

**Episodios:**

1. El médico indica que no existe información familiar.  
2. El sistema mantiene vacía la sección familiar.  
3. El sistema no crea familiares para el paciente.  
4. El registro del paciente continúa.

## **Escenario 20: Cambiar la contraseña inicial**

**Objetivo:** Permitir que el paciente establezca una contraseña propia.

**Contexto:** El médico creó al paciente y el sistema envió sus credenciales iniciales por correo electrónico.

**Actores:** Paciente.

**Recursos:** Usuario, contraseña inicial, nueva contraseña.

**Episodios:**

1. El paciente recibe sus credenciales.  
2. El paciente ingresa con la contraseña inicial.  
3. El sistema solicita cambiar la contraseña.  
4. El paciente establece una nueva contraseña.

## **Escenario 21: Registrar un médico**

**Objetivo:** Permitir que un médico se registre como usuario profesional.

**Contexto:** El profesional necesita utilizar el sistema.

**Actores:** Médico.

**Recursos:** Matrícula, especialidades, nombre, apellido, teléfono, correo electrónico.

**Episodios:**

1. El médico ingresa sus datos personales.  
2. El médico registra su matrícula.  
3. El médico selecciona sus especialidades.  
4. El sistema registra al médico.

## **Escenario 22: Registrar un administrativo**

**Objetivo:** Permitir que un administrativo se registre como usuario del sistema.

**Contexto:** El profesional administrativo necesita utilizar el sistema.

**Actores:** Administrativo.

**Recursos:** Nombre, apellido, teléfono, correo electrónico.

**Episodios:**

1. El administrativo ingresa sus datos personales.  
2. El administrativo registra sus datos de contacto.  
3. El sistema registra al administrativo.

## **Escenario 23: Gestionar una patología**

**Objetivo:** Registrar o modificar una patología y sus síntomas asociados.

**Contexto:** El gerente médico administra la información de las patologías disponibles.

**Actores:** Gerente médico.

**Recursos:** Patología, síntomas cardinales, síntomas secundarios.

**Episodios:**

1. El gerente médico registra una patología.  
2. El gerente médico registra sus síntomas cardinales.  
3. El gerente médico registra sus síntomas secundarios.  
4. El sistema guarda la información de la patología.

## **Escenario 24: Consultar variantes**

**Objetivo:** Consultar la clasificación de variantes genéticas asociadas a genes analizados.

**Contexto:** El bioinformático está analizando los genes de un estudio.

**Actores:** Bioinformático.

**Recursos:** Genes, variantes, clasificación de variantes.

**Episodios:**

1. El bioinformático selecciona un gen.  
2. El sistema consulta las variantes conocidas.  
3. El sistema muestra la clasificación de cada variante.  
4. El bioinformático utiliza la información para registrar el análisis.

## **Escenario 25: Consultar el chatbot sobre patologías**

**Objetivo:** Obtener respuestas sobre las cinco patologías contempladas por el sistema.

**Contexto:** El paciente tiene dudas sobre una de las patologías.

**Actores:** Paciente.

**Recursos:** Chatbot, información sobre patologías.

**Episodios:**

1. El paciente formula una pregunta.  
2. El sistema deriva la consulta al chatbot.  
3. El chatbot genera una respuesta.  
4. El sistema muestra la respuesta al paciente.

## **Escenario 26: Verificar el ingreso desde una máquina nueva** 

**Objetivo:** Confirmar la identidad del usuario cuando inicia sesión desde una máquina que el sistema no conoce. 

**Contexto:** El usuario ingresó sus credenciales correctamente desde una máquina nueva. 

**Actores:** Paciente; Médico; Gerente médico; Administrativo; Bioinformático; Transportista; Admin general. 

**Recursos:** Correo electrónico, código de verificación, dispositivo de acceso. 

**Episodios:**

1. El sistema detecta que el acceso se realiza desde una máquina nueva.  
2. El sistema envía un código de verificación al correo electrónico del usuario.  
3. El usuario ingresa el código.  
4. El sistema valida el código y habilita el acceso.

## **Escenario 27: Iniciar sesión** 

**Objetivo:** Permitir que un usuario registrado acceda de forma segura al sistema. 

**Contexto:** El usuario cuenta con credenciales (correo electrónico y contraseña) y necesita ingresar al sistema. 

**Actores:** Paciente; Médico; Gerente médico; Administrativo; Bioinformático; Transportista; Admin general. 

**Recursos:** Correo electrónico, contraseña, contraseña inicial, código de verificación, dispositivo de acceso. 

**Episodios:**

1. El usuario ingresa su correo electrónico y su contraseña.  
2. El sistema valida las credenciales.  
3. El sistema solicita cambiar la contraseña cuando es el primer ingreso.  
4. El sistema detecta que el acceso se realiza desde una máquina conocida.  
5. El sistema habilita el acceso al usuario.

## **Escenario 28: Cerrar sesión** 

**Objetivo:** Permitir que un usuario finalice su sesión de forma segura. 

**Contexto:** El usuario inició sesión y quiere terminar de usar el sistema, por ejemplo al retirarse de un equipo compartido. 

**Actores:** Paciente; Médico; Gerente médico; Administrativo; Bioinformático; Transportista; Admin general. 

**Recursos:** Sesión activa, dispositivo de acceso. 

**Episodios:**

1. El usuario solicita cerrar sesión.  
2. El sistema finaliza la sesión.  
3. El sistema redirige al usuario a la pantalla de ingreso.  
4. El sistema impide acceder a las pantallas protegidas sin volver a iniciar sesión.

## **Escenario 29: Crear un cupón** 

**Objetivo:** Generar un cupón de descuento limitado para ser usado en el pago de un estudio. 

**Contexto:** El gerente médico quiere ofrecer un descuento a pacientes. 

**Actores:** Gerente médico.

 **Recursos:** Cupón, descuento, API de cupones, código QR o código numérico. 

**Episodios:**

1. El gerente médico solicita crear un cupón.  
2. El gerente médico define el descuento del cupón.  
3. El sistema pide el cupón a la API de cupones.  
4. El sistema registra el cupón con su código.

## **Escenario 30: Asignar y aplicar un cupón** 

**Objetivo:** Entregar un cupón a un paciente y que este lo utilice al pagar su estudio. 

**Contexto:** Existe un cupón creado y un paciente con un estudio pendiente de pago. 

**Actores:** Médico tratante; Paciente. 

**Recursos:** Cupón, paciente, presupuesto, API de cupones. 

**Episodios:**

1. El médico asigna el cupón al paciente.  
2. El paciente aplica el cupón al pagar el presupuesto.  
3. El sistema consulta a la API de cupones si el cupón está vigente.  
4. El sistema aplica el descuento, que se acumula con la cobertura de la obra social.  
5. El sistema avisa a la API de cupones que el cupón fue usado, para que venza.

## **Escenario 31: Registrar un gerente médico** 

**Objetivo:** Dar de alta a un gerente médico como usuario con facultades adicionales. 

**Contexto:** El laboratorio necesita un usuario que administre patologías y cupones. 

**Actores:** Admin general. 

**Recursos:** Matrícula, especialidades, nombre, apellido, teléfono, correo electrónico. 

**Episodios:**

1. El admin general ingresa los datos personales del gerente médico.  
2. El admin general registra su matrícula.  
3. El admin general selecciona sus especialidades.  
4. El sistema registra al gerente médico.

## **Escenario 32: Seguir una muestra en el mapa** 

**Objetivo:** Mostrar por dónde viaja la muestra de un paciente mientras es trasladada. 

**Contexto:** La muestra fue retirada del centro de extracción y está en camino al laboratorio central. 

**Actores:** Paciente; Transportista. 

**Recursos:** Mapa de seguimiento, muestra, orden del día, estado del estudio. 

**Episodios:**

1. El transportista marca la recogida de la muestra en el centro de extracción.  
2. El sistema registra la muestra como en camino al laboratorio central.  
3. El paciente consulta el mapa de seguimiento.  
4. El sistema muestra la posición de la muestra.  
5. El transportista marca la llegada al laboratorio central.

## **Escenario 33: Ausentarse a un turno de extracción** 

**Objetivo:** Registrar la ausencia del paciente a un turno y aplicar el límite de cinco ausencias. 

**Contexto:** El paciente pagó el estudio (o fue autorizado) y no concurre al turno que sacó. 

**Actores:** Paciente. 

**Recursos:** Turno, contador de ausencias, estudio, pago. 

**Episodios:**

1. El paciente no concurre al turno de extracción.  
2. El sistema registra la ausencia.  
3. El sistema permite al paciente sacar un nuevo turno, hasta la quinta ausencia.  
4. Al llegar a la quinta ausencia, el sistema hace que el paciente pierda el pago.  
5. El sistema devuelve el estudio al estado Creado, y el paciente debe pagar de nuevo.

## **Escenario 34: Cambiar la contraseña** 

**Objetivo:** Que un usuario registrado reemplace su contraseña actual por una nueva cuando quiera. 

**Contexto:** El usuario ya inició sesión, ya cambió su contraseña inicial y quiere cambiarla por otra. 

**Actores:** Paciente; Médico; Gerente médico; Administrativo; Bioinformático; Transportista; Admin general. 

**Recursos:** Sesión activa, contraseña actual, nueva contraseña. 

**Episodios:**

1. El usuario solicita cambiar su contraseña.  
2. El usuario ingresa su contraseña actual.  
3. El usuario ingresa la nueva contraseña.  
4. El sistema valida la contraseña actual.  
5. El sistema registra la nueva contraseña.  
6. El usuario usa la nueva contraseña en los próximos ingresos.

## **Escenario 35:Grabar la historia clínica**  

## **Objetivo:** Cargar la historia clínica del paciente dictándola en lugar de escribirla. 

## **Contexto:** El médico está dando de alta a un paciente durante la consulta y prefiere grabar el resumen de su historia clínica. 

## **Actores:** Médico tratante. 

## **Recursos:** Grabación de audio, transcriptor de audio, historia clínica**.** 

## **Episodios:**

1. ## El médico graba la historia clínica del paciente.

2. ## El sistema envía la grabación al transcriptor de audio.

3. ## El transcriptor de audio convierte la grabación en texto.

4. ## El sistema guarda el texto como historia clínica del paciente.

## **Escenario 36: Cargar los síntomas del paciente con SNOMED** 

**Objetivo:** Registrar los síntomas del paciente con terminología estandarizada y validarlos contra la patología sospechada. 

**Contexto:** El médico está dando de alta a un paciente, ya indicó el diagnóstico presuntivo y debe cargar sus síntomas. 

**Actores:** Médico tratante. 

**Recursos:** SNOMED, lista de síntomas, diagnóstico presuntivo, patología, síntoma cardinal, síntomas secundarios. 

**Episodios:**

1. El médico escribe las primeras letras de un síntoma.  
2. El sistema consulta SNOMED y muestra una lista de síntomas coincidentes.  
3. El médico elige el síntoma de la lista.  
4. El sistema agrega el síntoma a la lista del paciente.  
5. El sistema valida los síntomas contra la patología: debe haber un síntoma cardinal o al menos dos síntomas secundarios.  
6. El sistema no permite dar de alta al paciente si la validación falla.

## **Escenario 37: Descargar el resultado de un estudio** 

**Objetivo:** Que el paciente descargue el PDF con el resultado de su estudio y que el médico lo reciba. 

**Contexto:** El bioinformático cargó las variantes y el estudio está en estado Resultado cargado. 

**Actores:** Paciente; Médico tratante. 

**Recursos:** Resultado en PDF, estudio, variantes del paciente, mail de aviso. 

**Episodios:**

1. El sistema envía un mail al paciente y al médico avisando que el resultado está disponible.  
2. El paciente ingresa al sistema.  
3. El paciente selecciona el estudio.  
4. El sistema muestra el resultado, que informa si fue positivo o negativo y las variantes del paciente.  
5. El paciente descarga el resultado en PDF.  
6. El médico recibe el resultado.

