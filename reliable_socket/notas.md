# Notas para ReliableSocket

 - [x] Firmas de los métodos básicos a implementar

## Connect
Lo primero que tengo que hacer es ver como se inicia una conexión.
SYN, ACK, SYN_ACK.
Esto además seguro guarde datos en algún tipo de estructura


## IMPORTANTE
 - [ ] El Server se comunica con todos los clientes a traves del mismo socket. 
 Siendo que el servidor envia data a los clientes en threads separados, es muy factible que
 necesitemos un **LOCK** para realizar el send. Validar
