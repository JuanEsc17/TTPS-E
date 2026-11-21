# **Glosario LEL – Laboratorio de Exoma Clínico**

# **SUJETOS**

## **Sujeto: Admin general**

**Noción:** Usuario que gestiona la **alta** de usuarios del sistema, en particular de los **gerentes médicos**.

**Impacto:**

* El **admin general** da de alta a los **gerentes médicos**.
* El **admin general** da de alta a los **administrativos**.

## **Sujeto: Administrativo**

**Noción:** Persona del **laboratorio central** a la que el **admin general** da de alta con nombre, apellido, teléfono y mail, y que gestiona los trámites del **estudio**.

**Impacto:**

* El **administrativo** emite el **presupuesto** del **estudio**.  
* El **administrativo** carga si la **obra social** autorizó o rechazó el **estudio**.  
* El **administrativo** carga los **datos crudos** recibidos de Corea.  
* El **administrativo** programa el **retiro** del **sample set** con **FedEx**.  
* El **administrativo** ve las **cuotas** de los **pacientes** (pagadas, pendientes, vencidas y anuladas).  
* El **administrativo** indica que se necesita **remuestrear** y retrocede el **estudio** a **Remuestreo requerido** cuando la **muestra** llega a Corea con baja calidad.  
* El **administrativo** no puede darse de baja ni borrar su información.

## **Sujeto: Bioinformático**

**Noción:** Integrante del equipo de bioinformática que analiza los **datos crudos**; se da de alta con nombre, apellido, mail y teléfono. El equipo comparte un solo mail.

**Impacto:**

* El **bioinformático** recibe un aviso en el mail del equipo cuando un **estudio** pasa a **En análisis por bioinformática**.  
* El **bioinformático** toma un **estudio** y lo pasa a **En análisis de un bioinformático**.  
* El **bioinformático** elige un **gen** y selecciona las **variantes** encontradas.  
* El **bioinformático** carga las **variantes** en el **estudio**.  
* El **bioinformático** ve primero los **estudios** de **Pompe urgente**.  
* El **bioinformático** no puede darse de baja ni borrar su información.

## **Sujeto: Gerente médico**

**Noción: Médico** con facultades adicionales; el **admin general** lo da de alta con los mismos datos que un **médico**.

**Impacto:**

* El **gerente médico** crea **cupones** y define su descuento.  
* El **gerente médico** asigna **cupones** a los **médicos**.  
* El **gerente médico** da de alta las **patologías**.  
* El **gerente médico** define el **síntoma cardinal** y los **síntomas secundarios** de cada **patología**.  
* El **gerente médico** modifica una **patología**.

## **Sujeto: Médico**

**Noción:** Profesional que se da de alta con matrícula, **especialidades**, nombre, apellido, teléfono y mail, y deriva pacientes desde la consulta inicial. Sinónimos: médico tratante, médico derivante.

**Impacto:**

* El **médico** da de alta al **paciente** si no existe.  
* El **médico** da de alta el **estudio** del **paciente**.  
* El **médico** graba la **historia clínica** con el **transcriptor de audio**.  
* El **médico** carga los **síntomas** con **SNOMED**.  
* El **médico** carga los **familiares** y envía el **familiograma**.  
* El **médico** elige los **genes** y puede agregar **genes** manualmente.  
* El **médico** marca si desea **hallazgos secundarios**.  
* El **médico** asigna **cupones** a los **pacientes**.  
* El **médico** solicita el **reanálisis**.  
* El **médico** recibe un mail cuando se carga el **resultado**.  
* El **médico** autorizado por el **paciente** puede consultar su **historia clínica**.  
* El **médico** puede ver desde un **estudio** de un **paciente** los **estudios** vinculados de sus **familiares** del **familiograma**.  
* El sistema asume que la matrícula del **médico** es válida.  
* El **médico** no puede cancelar un **turno** ni darse de baja.

## **Sujeto: Paciente**

**Noción:** Persona para quien se pide un **estudio**; accede al sistema con usuario y contraseña. Si es menor de edad, el padre realiza el proceso.

**Impacto:**

* El **paciente** cambia la contraseña en su primer ingreso.  
* El **paciente** paga el **presupuesto** (en un solo pago o en **cuotas** mediante **MercadoPago**) o espera la autorización de la **obra social**.  
* El **paciente** aplica un **cupón** al pagar.  
* El **paciente** abona las **cuotas** pendientes de su plan de pagos con **MercadoPago**.  
* El **paciente** puede agregar a varios **médicos** para autorizarlos a ver su **historia clínica** (y revocar la autorización).  
* El **paciente** elige un **turno** en un **centro de extracción**.  
* El **paciente** cancela el **turno**.  
* El **paciente** pierde el pago (y se anulan sus **cuotas** pendientes) si falta cinco veces a un **turno**.  
* El **paciente** descarga el **resultado**.  
* El **paciente** carga una **demanda** y su documentación si la **obra social** rechaza el **estudio**.  
* El **paciente** consulta al **chatbot**.  
* El **paciente** no puede darse de baja ni borrar su información.

## **Sujeto: Transportista**

**Noción:** Persona que traslada las **muestras** desde los **centros de extracción** hasta el **laboratorio central**; hay uno por provincia.

**Impacto:**

* El **transportista** recibe la **orden del día**.  
* El **transportista** marca la **recogida** en cada **centro de extracción**.  
* El **transportista** marca la llegada al **laboratorio central**.  
* El **transportista** no puede modificar la **orden del día**.

# **OBJETOS**

## **Objeto: API de bioinformática**

**Noción:** Módulo externo que informa los **genes** de cada **patología**, los **genes** de **hallazgos secundarios**, las **variantes** de cada **gen** y su clasificación.

**Impacto:**

* El sistema consulta la **API de bioinformática** para obtener los **genes**.  
* El sistema consulta la **API de bioinformática** para listar las **variantes** de un **gen**.

## **Objeto: API de cupones**

**Noción:** Módulo externo que genera **cupones** con QR y valida su vigencia.

**Impacto:**

* El sistema pide un **cupón** a la **API de cupones** cuando el **gerente médico** lo crea.  
* El sistema consulta si el **cupón** está vigente.  
* El sistema avisa que el **cupón** fue usado para que venza.

## **Objeto: API de familiograma**

**Noción:** Módulo externo que recibe los **familiares** y devuelve el **familiograma** en PDF.

**Impacto:**

* El sistema envía los parentescos a la **API de familiograma**.  
* El sistema asocia el PDF recibido al **paciente**.

## **Objeto: API de obras sociales**

**Noción:** Módulo externo con la lista de **obras sociales** y sus porcentajes de cobertura.

**Impacto:**

* El sistema consulta la **API de obras sociales** para mostrar la cobertura al **paciente**.

## **Objeto: API de MercadoPago**

**Noción:** Pasarela de pagos externa (sinónimo: **MercadoPago**) que genera preferencias de cobro y notifica el resultado de pagos únicos o en **cuotas** mediante webhooks.

**Impacto:**

* El sistema crea preferencias de cobro en **MercadoPago** cuando el **paciente** inicia el pago del **presupuesto** o de una **cuota**.  
* **MercadoPago** notifica al sistema la aprobación o rechazo del pago para habilitar **sacar turno** y actualizar el estado de la **cuota**.

## **Objeto: API de optimización de recorridos**

**Noción:** Módulo externo posible que ordena el recorrido de la **orden del día**.

**Impacto:**

* El sistema envía las direcciones del **transportista** y recibe el orden del recorrido.

## **Objeto: API del Ministerio de Salud**

**Noción:** Módulo externo que recibe el **CSV** y devuelve la **autorización del Ministerio**.

**Impacto:**

* El sistema envía el **CSV** a la **API del Ministerio de Salud** sin intervención del **administrativo**.  
* El sistema asocia el PDF recibido a los **estudios** del **sample set**.

## **Objeto: Autorización del Ministerio**

**Noción:** PDF que permite enviar los **pacientes** del **sample set** a Corea; debe coincidir con las **muestras** del paquete.

**Impacto:**

* El sistema asocia la **autorización del Ministerio** a cada **estudio** del **sample set**.  
* La **autorización del Ministerio** viaja con el **sample set** a Corea.

## **Objeto: Autorización de historia clínica**

**Noción:** Permiso explícito otorgado por el **paciente** a uno o varios **médicos** para consultar su **historia clínica**.

**Impacto:**

* El **paciente** agrega a varios **médicos** para autorizarlos a ver su **historia clínica**.  
* El sistema valida esta autorización antes de permitir la lectura de la **historia clínica** a un **médico**.

## **Objeto: Cuota**

**Noción:** Cada una de las fracciones periódicas de pago de un **presupuesto** financiado en **cuotas** con **MercadoPago**, con número de cuota, monto, fecha de vencimiento y estado (`pendiente`, `pagada`, `vencida`, `rechazada`, `anulada`).

**Impacto:**

* El sistema genera las **cuotas** cuando el **paciente** opta por pago en **cuotas** vía **MercadoPago**.  
* El **paciente** abona cada **cuota** pendiente mediante **MercadoPago**.  
* El **administrativo** visualiza las **cuotas** de todos los **pacientes**.

## **Objeto: Aviso**

**Noción:** Notificación dentro del sistema, además del mail, que informa pendientes a los usuarios.

**Impacto:**

* El sistema muestra una lista de **avisos** al usuario.

## **Objeto: Bot de Telegram**

**Noción:** Número del **laboratorio central** que recibe el mensaje cuando se toma una **muestra**.

**Impacto:**

* El **centro de extracción** envía un mensaje al **bot de Telegram**.  
* El sistema pasa el **estudio** a **Lista para retirar** al recibir el mensaje.

## **Objeto: Centro de extracción**

**Noción:** Laboratorio tercerizado donde se toma la **muestra**; hay 100 en el país y no operan en el sistema.

**Impacto:**

* El **paciente** asiste al **centro de extracción** a la hora del **turno**.  
* El **centro de extracción** avisa al **bot de Telegram** que tomó la **muestra**.

## **Objeto: Chatbot**

**Noción:** Módulo externo que responde consultas del **paciente** sobre las **patologías**.

**Impacto:**

* El sistema envía la pregunta al **chatbot** y muestra la respuesta.

## **Objeto: Código de verificación**

**Noción:** Código que el sistema envía por mail para confirmar el ingreso desde una máquina nueva.

**Impacto:**

* El sistema envía el **código de verificación** al mail del usuario al **iniciar sesión** desde una máquina nueva.  
* El usuario ingresa el **código de verificación** para entrar.

## **Objeto: Consentimiento informado**

**Noción:** Documento que el **paciente** (o su padre) imprime, completa, firma y entrega; se gestiona fuera del sistema y no se guarda en él.

**Impacto:**

* El sistema envía el **consentimiento informado** al **paciente** al **sacar turno**.

## **Objeto: CSV**

**Noción:** Archivo con los **pacientes** del **sample set**, requerido por el **Ministerio de Salud**.

**Impacto:**

* El sistema genera el **CSV** automáticamente al cerrarse el **sample set**.  
* El sistema asocia el **CSV** a los **estudios** del **sample set**.

## **Objeto: Cupón**

**Noción:** Descuento limitado, con QR o código numérico, creado por el **gerente médico**; se acumula con la cobertura de la **obra social**.

**Impacto:**

* El **médico** asigna el **cupón** a un **paciente**.  
* El **paciente** aplica el **cupón** al pagar.  
* La **API de cupones** vence el **cupón** al usarse.

## **Objeto: Datos crudos**

**Noción:** Archivo de texto con letras A, C, T y G que llega de Corea; por ahora se simula.

**Impacto:**

* El **administrativo** carga los **datos crudos** del **estudio**.  
* El **bioinformático** analiza los **datos crudos** y encuentra **variantes**.

## **Objeto: Demanda**

**Noción:** Reclamo del **paciente** cuando la **obra social** rechaza el **estudio**, con documentación judicial favorable en PDF.

**Impacto:**

* El **paciente** carga la **demanda** asociada al **estudio**.  
* El sistema habilita la reautorización del **estudio**.

## **Objeto: Especialidad**

**Noción:** Área médica estandarizada que el **médico** elige al darse de alta; la lista debe ser lo más completa posible.

**Impacto:**

* El **médico** elige sus **especialidades** de la lista.

## **Objeto: Estudio**

**Noción:** Exoma clínico que analiza el ADN del **paciente** para buscar **variantes** en ciertos **genes**. Sinónimo: **sample**.

**Impacto:**

* El **médico** da de alta el **estudio**.  
* El **estudio** pasa por distintos **estados** en un único circuito, pudiendo retroceder a **Remuestreo requerido** si la **muestra** llega a Corea con baja calidad.  
* El **estudio** tiene un precio fijo de 500 dólares hasta 5 **genes** y 30 dólares por **gen** adicional.  
* El **estudio** guarda la fecha en que corresponde realizar un nuevo **estudio** dentro de un año cuando el diagnóstico es **VUS**.  
* El **estudio** se vincula automáticamente con los **estudios** de **familiares** que figuren en el **familiograma**.  
* Toda modificación sobre el **estudio** queda asentada en el **registro de modificaciones**.

## **Objeto: Familiar**

**Noción:** Pariente del **paciente**, con parentesco, nombre, apellido opcional, DNI opcional, **síntomas** y diagnóstico previo, si lo hay.

**Impacto:**

* El **médico** carga cada **familiar** del **paciente**.  
* El sistema envía los **familiares** a la **API de familiograma**.  
* Si el **familiar** se registra como **paciente** y se realiza un **estudio**, el sistema vincula automáticamente su **estudio** con los **estudios** del **paciente** original.

## **Objeto: Familiograma**

**Noción:** Dibujo en PDF de la familia del **paciente** que muestra el patrón de herencia. Sinónimo: genograma.

**Impacto:**

* La **API de familiograma** devuelve el **familiograma**.  
* El sistema asocia el **familiograma** al **paciente**.

## **Objeto: Gen**

**Noción:** Región del ADN que codifica una proteína; se asocia a una **patología**.

**Impacto:**

* El **médico** elige los **genes** a analizar.  
* El **bioinformático** elige el **gen** para cargar **variantes**.

## **Objeto: Hallazgo secundario**

**Noción: Genes** adicionales, en cantidad variable, no asociados a la **patología** sospechada, que el **médico** puede pedir analizar.

**Impacto:**

* El **médico** marca si desea **hallazgos secundarios**.  
* La **API de bioinformática** informa los **genes** correspondientes.

## **Objeto: Historia clínica**

**Noción:** Resumen de la salud del **paciente** que el **médico** carga al dar de alta al **paciente**.

**Impacto:**

* El **médico** graba la **historia clínica** y el **transcriptor de audio** la convierte en texto.  
* El **paciente** puede agregar a varios **médicos** con autorización para ver su **historia clínica**.  
* Toda modificación sobre el **paciente** (incluida su **historia clínica**) queda asentada en el **registro de modificaciones**.

## **Objeto: Mapa de seguimiento**

**Noción:** Mapa que muestra por dónde viaja la **muestra** de un **paciente** con el **transportista**.

**Impacto:**

* El sistema muestra en el **mapa de seguimiento** la posición de la **muestra**.

## **Objeto: Muestra**

**Noción:** Muestra de sangre del **paciente** para el **estudio**.

**Impacto:**

* El **paciente** entrega la **muestra** en el **centro de extracción**.  
* El **transportista** traslada la **muestra** al **laboratorio central**.  
* El sistema agrupa las **muestras** en **sample sets**.  
* Si cuando llega la **muestra** a Corea tiene baja calidad (o no sirve para secuenciación), el **administrativo** indica que se necesita **remuestrear** y retrocede el **estudio**. (No existe descarte ni mínimo por muestra menor a 2 mililitros).

## **Objeto: Obra social**

**Noción:** Entidad que puede cubrir el **presupuesto** con un porcentaje propio de cobertura.

**Impacto:**

* La **obra social** autoriza o rechaza el **estudio**.  
* La **obra social** paga el **estudio** una vez autorizado.

## **Objeto: Orden de extracción**

**Noción:** Documento con fecha, hora y datos del **turno** que recibe el **paciente**.

**Impacto:**

* El sistema envía la **orden de extracción** al **paciente** al **sacar turno**.

## **Objeto: Orden del día**

**Noción:** Recorrido fijo y ordenado de **centros de extracción** que el **transportista** recibe cada mañana; no se genera en feriados ni fines de semana.

**Impacto:**

* El sistema genera la **orden del día** con la **API de optimización de recorridos**.  
* El **transportista** no puede modificar la **orden del día**.

## **Objeto: Patología**

**Noción:** Enfermedad lisosomal que maneja el laboratorio (Fabry, Pompe, mucopolisacaridosis 1, Gaucher, ASMD), con un **síntoma cardinal** y **síntomas secundarios**.

**Impacto:**

* El **gerente médico** da de alta y modifica la **patología**.  
* El **médico** elige la **patología** como diagnóstico presuntivo.  
* El sistema valida los **síntomas** contra la **patología**.

## **Objeto: Pompe urgente**

**Noción: Estudio** de Pompe de un menor de 4 meses, que puede viajar sin completar el **sample set**.

**Impacto:**

* El sistema cierra el **sample set** al llegar un **Pompe urgente**.  
* El **bioinformático** ve el **Pompe urgente** primero en su lista.

## **Objeto: Presupuesto**

**Noción:** Costo del **estudio**, que incluye la extracción, a pagar de forma particular (en un solo pago o en **cuotas** con **MercadoPago**) o cubierto por **obra social**.

**Impacto:**

* El **administrativo** emite el **presupuesto**.  
* El **paciente** paga el **presupuesto** (en un pago o en **cuotas** vía **API de MercadoPago**) o lo cubre la **obra social**.  
* El sistema registra el pago y sus **cuotas** financieramente.

## **Objeto: Recordatorio**

**Noción:** Mail que el sistema envía por cada **turno** con fecha, hora y el límite de 5 ausencias.

**Impacto:**

* El sistema envía el **recordatorio** al **paciente** al **sacar turno**.

## **Objeto: Registro de modificaciones**

**Noción:** Historial inmutable (solo inserción) de todas las altas, modificaciones y transiciones realizadas sobre **sample sets**, **pacientes** y **estudios**.

**Impacto:**

* El sistema registra automáticamente el responsable (usuario o proceso del sistema), fecha y hora, entidad, cambios realizados y motivo cada vez que se crea o modifica un **sample set**, **paciente** o **estudio**.

## **Objeto: Resultado**

**Noción:** PDF con la conclusión diagnóstica (positividad, negatividad o **VUS**) del **estudio** y las **variantes** del **paciente**.

**Impacto:**

* El sistema notifica por mail al **médico** y al **paciente** al cargar el **resultado**.  
* Si el diagnóstico es **VUS**, el sistema guarda la fecha en que corresponde realizar un nuevo **estudio** dentro de un año y la informa en el resultado.  
* El **paciente** descarga el **resultado**.

## **Objeto: Sample set**

**Noción:** Lote de 10 **muestras** enviado a Corea; solo se envía incompleto en **Pompe urgente**.

**Impacto:**

* El sistema arma el **sample set** al llegar las **muestras**.  
* El sistema cierra el **sample set** al completarse 10 **muestras** o al llegar un **Pompe urgente**.  
* El **administrativo** programa el **retiro** del **sample set**.  
* El sistema no admite más **muestras** una vez que el **sample set** se cierra.  
* Toda modificación sobre el **sample set** queda asentada en el **registro de modificaciones**.

## **Objeto: SNOMED**

**Noción:** Estándar de terminología médica para codificar **síntomas**.

**Impacto:**

* El **médico** busca **síntomas** en **SNOMED** al escribir.

## **Objeto: Síntoma**

**Noción:** Signo del **paciente** o **familiar**, codificado en **SNOMED**. Puede ser **síntoma cardinal** o **síntoma secundario**.

**Impacto:**

* El **médico** carga los **síntomas** del **paciente**.  
* El sistema valida los **síntomas** contra la **patología**.

## **Objeto: Síntoma cardinal**

**Noción: Síntoma** principal de una **patología**.

**Impacto:**

* El **gerente médico** define el **síntoma cardinal**.  
* Un **síntoma cardinal** valida el alta del **paciente**.

## **Objeto: Síntoma secundario**

**Noción: Síntoma** no principal de una **patología**.

**Impacto:**

* Dos **síntomas secundarios** validan el alta del **paciente** si no hay **síntoma cardinal**.

## **Objeto: Transcriptor de audio**

**Noción:** Herramienta que convierte en texto la grabación del **médico**.

**Impacto:**

* El **médico** usa el **transcriptor de audio** para cargar la **historia clínica**.

## **Objeto: Turno**

**Noción:** Horario de 15 minutos en un **centro de extracción** para una sola persona, de lunes a viernes de 9 a 18, salvo feriados.

**Impacto:**

* El **paciente** elige un **turno** libre en un mapa.  
* El **paciente** cancela el **turno**.  
* El sistema envía un **recordatorio** por cada **turno**.

## **Objeto: Variante**

**Noción:** Letra del ADN del **paciente** distinta del genoma de referencia, clasificada como patogénica, benigna, inocua o **VUS**.

**Impacto:**

* El **bioinformático** selecciona la **variante** de la lista del **gen**.  
* El diagnóstico es positivo si la **variante** es patogénica.

## **Objeto: Vínculo de estudios familiares**

**Noción:** Asociación bidireccional automática entre los **estudios** de un **paciente** y los **estudios** de un **familiar** presente en su **familiograma** que también se realiza un **estudio**.

**Impacto:**

* El sistema vincula automáticamente ambos registros en la tabla de estudios vinculados al darse de alta el **estudio** o vincularse el **familiar**.  
* El **médico** puede ver y navegar desde el **estudio** de un paciente hacia el **estudio** del familiar vinculado.

## **Objeto: VUS**

**Noción: Variante** de significado incierto, sin evidencia suficiente para clasificarla como patogénica o benigna.

**Impacto:**

* La **API de bioinformática** puede clasificar una **variante** como **VUS**.  
* Si el diagnóstico del **estudio** resulta **VUS**, el sistema guarda la fecha para realizar un nuevo **estudio** dentro de un año (`fecha_resultado + 1 año`).

# **VERBOS**

## **Verbo: Armar sample set**

**Noción:** Agrupar **muestras** en 10 para evitar costos de envío.

**Impacto:**

* El sistema agrega las **muestras** al **sample set** al llegar al **laboratorio central**.  
* El sistema cierra el **sample set** al llegar a 10 o ante un **Pompe urgente**.

## **Verbo: Cancelar turno**

**Noción:** Liberar el **turno** elegido.

**Impacto:**

* El **paciente** cancela el **turno**.  
* El **médico** no puede cancelar un **turno**.

## **Verbo: Cargar resultado**

**Noción:** Registrar las **variantes** del **estudio** para informar al **médico** y al **paciente**.

**Impacto:**

* El **bioinformático** carga las **variantes** en el **estudio**.  
* El **estudio** pasa a **Resultado cargado** y se registra la modificación.  
* Si el diagnóstico es **VUS**, el sistema guarda la fecha en que se debe realizar un nuevo **estudio** dentro de un año.  
* El sistema notifica por mail al **médico** y al **paciente**.

## **Verbo: Dar de alta estudio**

**Noción:** Registrar un **estudio** para un **paciente**.

**Impacto:**

* El **médico** elige el **paciente**, los **genes** y los **hallazgos secundarios**.  
* El **estudio** pasa a **Creado**.

## **Verbo: Dar de alta paciente**

**Noción:** Registrar al **paciente** con datos obligatorios, salvo el **familiograma**.

**Impacto:**

* El **médico** carga DNI, nombre, apellido, teléfono, mail, fecha de nacimiento, diagnóstico presuntivo, **historia clínica**, **síntomas** y tipo de sospecha.  
* El sistema valida los **síntomas** contra la **patología**.  
* El sistema envía al **paciente** un mail con usuario y contraseña.

## **Verbo: Iniciar sesión**

**Noción:** Identificar al usuario y autorizarlo a ingresar al sistema, con contraseña.

**Impacto:**

* El usuario ingresa usuario y contraseña.  
* El sistema pide un **código de verificación** si el usuario ingresa desde una máquina nueva.

## **Verbo: Pagar presupuesto**

**Noción:** Abonar el **presupuesto** en un solo pago o en **cuotas** mediante la **API de MercadoPago**.

**Impacto:**

* El **paciente** elige cantidad de **cuotas** (1 o más), puede aplicar un **cupón** y abona mediante **MercadoPago**.  
* El sistema registra el pago y sus **cuotas**, habilitando **sacar turno** tras la confirmación del pago único o primera **cuota**.

## **Verbo: Pagar cuota**

**Noción:** Abonar una **cuota** pendiente o vencida de un plan de pago mediante **MercadoPago**.

**Impacto:**

* El **paciente** genera la preferencia en **MercadoPago** para la **cuota** y el sistema actualiza el estado de la **cuota** a pagada al confirmarse el webhook.

## **Verbo: Consultar cuotas**

**Noción:** Visualizar las **cuotas** de los **pacientes**, sus vencimientos, estados y operaciones de **MercadoPago**.

**Impacto:**

* El **administrativo** consulta y filtra las **cuotas** de los **pacientes** para seguimiento de caja y deudas.

## **Verbo: Autorizar médico a historia clínica**

**Noción:** Otorgar o revocar permiso a uno o varios **médicos** para ver la **historia clínica** del **paciente**.

**Impacto:**

* El **paciente** agrega a varios **médicos** en su lista de autorizados y el sistema les habilita el acceso de lectura a su **historia clínica**.

## **Verbo: Vincular estudios familiares**

**Noción:** Asociar automáticamente el **estudio** de un **familiar** del **familiograma** con los **estudios** del **paciente** original y permitir su visualización cruzada por el **médico**.

**Impacto:**

* El sistema crea el **vínculo de estudios familiares** al registrarse el **estudio** del familiar.  
* El **médico** accede desde el **estudio** de un paciente al **estudio** vinculado de su familiar.

## **Verbo: Registrar modificación**

**Noción:** Persistir de manera inmutable cada creación o cambio realizado sobre **sample sets**, **pacientes** o **estudios**.

**Impacto:**

* Toda operación de alta, actualización o cambio de estado sobre **sample sets**, **pacientes** o **estudios** genera una entrada en el **registro de modificaciones**.

## **Verbo: Reanalizar estudio**

**Noción:** Analizar otros **genes** del mismo ADN sin repetir la **muestra**.

**Impacto:**

* El **médico** solicita el **reanálisis**.  
* El **reanálisis** usa el mismo **estudio**.

## **Verbo: Remuestrear**

**Noción:** Retroceder el **estudio** y tomar una nueva **muestra** al **paciente** cuando la muestra llega a Corea con baja calidad (u otro fallo de calidad, sin regla de menos de 2 mililitros), sin costo para él.

**Impacto:**

* El **administrativo** indica que se necesita un remuestreo y retrocede el **estudio** a **Remuestreo requerido**.  
* El sistema notifica por mail al **médico** y al **paciente** y registra la modificación.  
* El **paciente** saca un nuevo **turno** para el mismo **estudio**.

## **Verbo: Retirar sample set**

**Noción:** Recoger el **sample set** sellado por **FedEx** para enviarlo a Corea.

**Impacto:**

* El **administrativo** programa día, hora y URL de **retiro**.  
* El sistema cambia el **estado** del **sample set** y sus **estudios** a **En viaje a Corea**.

## **Verbo: Sacar turno**

**Noción:** Reservar un **turno** en un **centro de extracción** tras el pago o la autorización.

**Impacto:**

* El **paciente** elige un **centro de extracción** en el mapa y un **turno** libre.  
* El sistema envía la **orden de extracción**, el **consentimiento informado** y el **recordatorio**.

## **Verbo: Cerrar sesión**

**Noción:**Finalizar el acceso del usuario al sistema para que nadie más pueda usar su cuenta desde ese equipo. 

**Impacto:**

* El usuario solicita cerrar sesión.   
* El sistema finaliza la sesión.   
* El sistema redirige al usuario a la pantalla de ingreso.  
* El sistema impide acceder a las pantallas protegidas sin volver a iniciar sesión 

## **Verbo: Descargar resultado** 

**Noción:** Bajar el PDF del resultado desde el sistema.  
**Impacto:**

* El paciente descarga el resultado.  
* El médico recibe el resultado.  
* El resultado informa si fue positivo o negativo y las variantes del paciente.

## **Verbo: Cargar síntomas** 

**Noción:** Registrar los síntomas del paciente usando terminología estandarizada SNOMED.  
**Impacto:**

* El médico escribe las primeras letras del síntoma.  
* El sistema consulta SNOMED y muestra una lista de coincidencias.  
* El médico elige el síntoma de la lista.  
* El sistema valida los síntomas contra la patología.

## **Verbo: Grabar historia clínica** 

**Noción:** Registrar la historia clínica del paciente dictándola en lugar de escribirla.  
**Impacto:**

* El médico graba la historia clínica.  
* El transcriptor de audio la convierte en texto.  
* El sistema guarda el texto como historia clínica del paciente.

## **Verbo: Cambiar contraseña inicial** 

**Noción:** Reemplazar la contraseña inicial por una propia, obligatorio en el primer ingreso del paciente.  
**Impacto:**

* El sistema pide el cambio de contraseña en el primer ingreso del paciente.  
* El paciente establece su nueva contraseña.  
* El paciente ya puede ingresar con la nueva contraseña.

## **Verbo: Cambiar contraseña** 

**Noción:** Reemplazar la contraseña actual por una nueva cuando el usuario lo desee, después del primer ingreso.  
**Impacto:**

* El usuario solicita cambiar su contraseña.  
* El usuario ingresa su contraseña actual y la nueva.  
* El sistema valida la contraseña actual.  
* El sistema registra la nueva contraseña.

# **ESTADOS**

## **Estado: Autorizado**

**Noción:** Situación del **estudio** aprobado por la **obra social**, asumido como pagado.

**Impacto:**

* El **administrativo** marca el **estudio** como **Autorizado**.  
* El sistema notifica al **paciente** y habilita **Sacar turno**.

## **Estado: Creado**

**Noción:** Situación inicial del **estudio** tras el alta, a la espera del pago.

**Impacto:**

* El **paciente** paga el **presupuesto** (pago único o primera **cuota** con **MercadoPago**) y puede **sacar turno**.  
* El **estudio** pasa a **Turno sacado** cuando el **paciente** saca el **turno**.  
* El **estudio** pasa a **Pendiente de autorización** si el **paciente** elige **obra social**.  
* El **estudio** vuelve a **Creado** si el **paciente** falta cinco veces, pierde el pago (se anulan las **cuotas** pendientes) y debe pagar de nuevo.

## **Estado: En análisis de un bioinformático**

**Noción:** Situación del **estudio** que un **bioinformático** tomó para analizar.

**Impacto:**

* El **bioinformático** carga las **variantes** y el **estudio** pasa a **Resultado cargado**.

## **Estado: En análisis por bioinformática**

**Noción:** Situación del **estudio** con **datos crudos** recibidos de Corea, disponible para el equipo de bioinformática. Sinónimo: En área bioinformática.

**Impacto:**

* El **administrativo** carga los **datos crudos** y el **estudio** pasa a **En análisis por bioinformática**.  
* Un **bioinformático** toma el **estudio** y pasa a **En análisis de un bioinformático**.

## **Estado: En camino al laboratorio central**

**Noción:** Situación del **estudio** cuya **muestra** lleva el **transportista**.

**Impacto:**

* El **transportista** marca la llegada y el **estudio** pasa a **En laboratorio central**.

## **Estado: En espera de retiro**

**Noción:** Situación del **estudio** cuyo **sample set** está sellado y aguarda a **FedEx**.

**Impacto:**

* El **administrativo** programa el **retiro** y, a la hora indicada, el **estudio** pasa a **En viaje a Corea**.

## **Estado: En laboratorio central**

**Noción:** Situación del **estudio** cuya **muestra** llegó al **laboratorio central**.

**Impacto:**

* El sistema arma el **sample set** con la **muestra**.  
* El sistema cierra el **sample set** y el **estudio** pasa a **En espera de retiro**.

## **Estado: En viaje a Corea**

**Noción:** Situación del **sample set** y sus **estudios** tras el **retiro**.

**Impacto:**

* El **administrativo** carga los **datos crudos** y el **estudio** pasa a **En análisis por bioinformática**.  
* Si la **muestra** llega a Corea con baja calidad, el **administrativo** indica el remuestreo y retrocede el **estudio** a **Remuestreo requerido**.

## **Estado: Lista para retirar**

**Noción:** Situación del **estudio** cuya **muestra** ya fue tomada en el **centro de extracción**.

**Impacto:**

* El **transportista** marca la **recogida** y el **estudio** pasa siempre a **En camino al laboratorio central**.

## **Estado: Pendiente de autorización**

**Noción:** Situación del **estudio** por **obra social** a la espera de decisión.

**Impacto:**

* El **administrativo** carga la autorización y pasa a **Autorizado**.  
* El **administrativo** carga el rechazo y pasa a **Rechazado**.

## **Estado: Rechazado**

**Noción:** Situación del **estudio** rechazado por la **obra social**.

**Impacto:**

* El **paciente** carga una **demanda** y pide la reautorización.  
* El **estudio** vuelve a **Pendiente de autorización**.

## **Estado: Remuestreo requerido**

**Noción:** Situación del **estudio** cuya **muestra** llegó a Corea con baja calidad (o presenta ADN insuficiente / desnaturalizado; sin restricción de menos de 2 mililitros) y debió retroceder.

**Impacto:**

* El **administrativo** marca que se necesita un remuestreo y retrocede el **estudio** a este estado.  
* El **paciente** saca un nuevo **turno** sin pagar de nuevo.  
* El **estudio** pasa a **Turno sacado**.

## **Estado: Resultado cargado**

**Noción:** Situación del **estudio** con **resultado** disponible.

**Impacto:**

* El sistema notifica por mail al **médico** y al **paciente**.  
* Si el diagnóstico es **VUS**, el sistema guarda la fecha para realizar un nuevo **estudio** dentro de un año.

## **Estado: Turno sacado**

**Noción:** Situación del **estudio** con **turno** reservado.

**Impacto:**

* El **paciente** asiste y el sistema pasa el **estudio** a **Lista para retirar** al recibir el mensaje del **bot de Telegram**.  
* Si el **paciente** falta de una a cuatro veces, saca otro **turno**.  
* Si el **paciente** falta cinco veces, el **estudio** vuelve a **Creado**.