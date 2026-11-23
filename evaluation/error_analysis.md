# Analisis de errores por corrida (Fase 6)

Generado por `evaluation/evaluate.py`. Cada servicio producido se asocia a la particion de la referencia
con mayor similitud (direccion P→R, metodo 2, la misma que usa el WS). Una clase esta **de más** en un
servicio si la particion asociada no la contiene en la referencia, y **falta** en una particion de
referencia si ningun servicio asociado a ella la contiene. Las clases `uncounted` no cuentan como error
(el WS las excluye); se indica donde quedaron.

## jpetstore-6 / claude-run4

| Servicio producido | ≈ Particion de referencia | Similitud |
|---|---|---|
| Account Management | account | 0.833 |
| Catalog | catalog | 0.900 |
| Shopping and Order Management | order | 0.846 |

| Clase | En la referencia | De más en | Falta en (referencia) |
|---|---|---|---|
| `CatalogService` | catalog | Account Management (~account), Shopping and Order Management (~order) | — |
| `CartActionBean` | catalog | Shopping and Order Management (~order) | catalog |

## jpetstore-6 / claude-run5

| Servicio producido | ≈ Particion de referencia | Similitud |
|---|---|---|
| Account Management | account | 1.000 |
| Catalog | catalog | 0.900 |
| Shopping Cart and Order Management | order | 0.917 |

| Clase | En la referencia | De más en | Falta en (referencia) |
|---|---|---|---|
| `CartActionBean` | catalog | Shopping Cart and Order Management (~order) | catalog |

## jpetstore-6 / claude-run6

| Servicio producido | ≈ Particion de referencia | Similitud |
|---|---|---|
| Account Management | account | 1.000 |
| Product Catalog | catalog | 0.900 |
| Shopping Cart and Order Management | order | 0.917 |

| Clase | En la referencia | De más en | Falta en (referencia) |
|---|---|---|---|
| `CartActionBean` | catalog | Shopping Cart and Order Management (~order) | catalog |

## jpetstore-6 / claude-run7

| Servicio producido | ≈ Particion de referencia | Similitud |
|---|---|---|
| Account Management | account | 0.556 |
| Catalog | catalog | 0.900 |
| Order & Cart Management | order | 0.647 |

| Clase | En la referencia | De más en | Falta en (referencia) |
|---|---|---|---|
| `Account` | account | Order & Cart Management (~order) | — |
| `Item` | catalog | Account Management (~account), Order & Cart Management (~order) | — |
| `Product` | catalog | Account Management (~account), Order & Cart Management (~order) | — |
| `ItemMapper` | catalog | Account Management (~account), Order & Cart Management (~order) | — |
| `CatalogService` | catalog | Account Management (~account), Order & Cart Management (~order) | — |
| `CartActionBean` | catalog | Order & Cart Management (~order) | catalog |

## jpetstore-6 / claude-run8

| Servicio producido | ≈ Particion de referencia | Similitud |
|---|---|---|
| Account Management | account | 0.625 |
| Catalog | catalog | 0.900 |
| Shopping Cart and Order Management | order | 0.688 |

| Clase | En la referencia | De más en | Falta en (referencia) |
|---|---|---|---|
| `Account` | account | Shopping Cart and Order Management (~order) | — |
| `Item` | catalog | Account Management (~account), Shopping Cart and Order Management (~order) | — |
| `ItemMapper` | catalog | Account Management (~account), Shopping Cart and Order Management (~order) | — |
| `CatalogService` | catalog | Account Management (~account), Shopping Cart and Order Management (~order) | — |
| `CartActionBean` | catalog | Shopping Cart and Order Management (~order) | catalog |

## jpetstore-6 / claude-run9

| Servicio producido | ≈ Particion de referencia | Similitud |
|---|---|---|
| Account Management | account | 1.000 |
| Catalog | catalog | 0.900 |
| Shopping Cart and Order Management | order | 0.917 |

| Clase | En la referencia | De más en | Falta en (referencia) |
|---|---|---|---|
| `CartActionBean` | catalog | Shopping Cart and Order Management (~order) | catalog |

## jpetstore-6 / claude-run10

| Servicio producido | ≈ Particion de referencia | Similitud |
|---|---|---|
| Account Management | account | 0.833 |
| Catalog Management | catalog | 0.900 |
| Shopping Cart and Order Management | order | 0.846 |

| Clase | En la referencia | De más en | Falta en (referencia) |
|---|---|---|---|
| `CatalogService` | catalog | Account Management (~account), Shopping Cart and Order Management (~order) | — |
| `CartActionBean` | catalog | Shopping Cart and Order Management (~order) | catalog |

## jpetstore-6 / claude-run11

| Servicio producido | ≈ Particion de referencia | Similitud |
|---|---|---|
| Account Management | account | 0.833 |
| Catalog | catalog | 0.900 |
| Shopping Cart & Order Management | order | 0.846 |

| Clase | En la referencia | De más en | Falta en (referencia) |
|---|---|---|---|
| `CatalogService` | catalog | Account Management (~account), Shopping Cart & Order Management (~order) | — |
| `CartActionBean` | catalog | Shopping Cart & Order Management (~order) | catalog |

## jpetstore-6 / claude-run12

| Servicio producido | ≈ Particion de referencia | Similitud |
|---|---|---|
| Account Management | account | 1.000 |
| Catalog | catalog | 0.900 |
| Shopping Cart and Order Management | order | 0.917 |

| Clase | En la referencia | De más en | Falta en (referencia) |
|---|---|---|---|
| `CartActionBean` | catalog | Shopping Cart and Order Management (~order) | catalog |

## jpetstore-6 / claude-run13

| Servicio producido | ≈ Particion de referencia | Similitud |
|---|---|---|
| Account Management | account | 0.833 |
| Catalog | catalog | 0.900 |
| Shopping Cart and Order Management | order | 0.733 |

| Clase | En la referencia | De más en | Falta en (referencia) |
|---|---|---|---|
| `Item` | catalog | Shopping Cart and Order Management (~order) | — |
| `ItemMapper` | catalog | Shopping Cart and Order Management (~order) | — |
| `CatalogService` | catalog | Account Management (~account), Shopping Cart and Order Management (~order) | — |
| `CartActionBean` | catalog | Shopping Cart and Order Management (~order) | catalog |

## jpetstore-6 / baseline-run1

| Servicio producido | ≈ Particion de referencia | Similitud |
|---|---|---|
| AccountService | account | 1.000 |
| CatalogService | catalog | 0.833 |
| OrderService | order | 0.786 |

| Clase | En la referencia | De más en | Falta en (referencia) |
|---|---|---|---|
| `Account` | account | OrderService (~order) | — |
| `Cart` | order | CatalogService (~catalog) | — |
| `CartItem` | order | CatalogService (~catalog) | — |
| `Item` | catalog | OrderService (~order) | — |
| `ItemMapper` | catalog | OrderService (~order) | — |

## jpetstore-6 / baseline-run2

| Servicio producido | ≈ Particion de referencia | Similitud |
|---|---|---|
| AccountService | account | 1.000 |
| CatalogService | catalog | 0.833 |
| OrderService | order | 0.786 |

| Clase | En la referencia | De más en | Falta en (referencia) |
|---|---|---|---|
| `Account` | account | OrderService (~order) | — |
| `Cart` | order | CatalogService (~catalog) | — |
| `CartItem` | order | CatalogService (~catalog) | — |
| `Item` | catalog | OrderService (~order) | — |
| `ItemMapper` | catalog | OrderService (~order) | — |

## jpetstore-6 / baseline-run3

| Servicio producido | ≈ Particion de referencia | Similitud |
|---|---|---|
| AccountService | account | 1.000 |
| CatalogService | catalog | 0.833 |
| OrderService | order | 0.786 |

| Clase | En la referencia | De más en | Falta en (referencia) |
|---|---|---|---|
| `Account` | account | OrderService (~order) | — |
| `Cart` | order | CatalogService (~catalog) | — |
| `CartItem` | order | CatalogService (~catalog) | — |
| `Item` | catalog | OrderService (~order) | — |
| `ItemMapper` | catalog | OrderService (~order) | — |

## jpetstore-6 / claude-run1

| Servicio producido | ≈ Particion de referencia | Similitud |
|---|---|---|
| Account Management | account | 1.000 |
| Catalog | catalog | 0.900 |
| Shopping Cart and Order Management | order | 0.917 |

| Clase | En la referencia | De más en | Falta en (referencia) |
|---|---|---|---|
| `CartActionBean` | catalog | Shopping Cart and Order Management (~order) | catalog |

## jpetstore-6 / claude-run2

| Servicio producido | ≈ Particion de referencia | Similitud |
|---|---|---|
| Account Management | account | 0.556 |
| Catalog | catalog | 0.900 |
| Shopping Cart and Order Management | order | 0.688 |

| Clase | En la referencia | De más en | Falta en (referencia) |
|---|---|---|---|
| `Account` | account | Shopping Cart and Order Management (~order) | — |
| `Item` | catalog | Account Management (~account), Shopping Cart and Order Management (~order) | — |
| `Product` | catalog | Account Management (~account) | — |
| `ItemMapper` | catalog | Account Management (~account), Shopping Cart and Order Management (~order) | — |
| `CatalogService` | catalog | Account Management (~account), Shopping Cart and Order Management (~order) | — |
| `CartActionBean` | catalog | Shopping Cart and Order Management (~order) | catalog |

## jpetstore-6 / claude-run3

| Servicio producido | ≈ Particion de referencia | Similitud |
|---|---|---|
| Account Management | account | 0.625 |
| Catalog | catalog | 0.900 |
| Shopping Cart and Order Management | order | 0.688 |

| Clase | En la referencia | De más en | Falta en (referencia) |
|---|---|---|---|
| `Account` | account | Shopping Cart and Order Management (~order) | — |
| `Item` | catalog | Account Management (~account), Shopping Cart and Order Management (~order) | — |
| `ItemMapper` | catalog | Account Management (~account), Shopping Cart and Order Management (~order) | — |
| `CatalogService` | catalog | Account Management (~account), Shopping Cart and Order Management (~order) | — |
| `CartActionBean` | catalog | Shopping Cart and Order Management (~order) | catalog |

## jpetstore-6 / claude-run1-e4-r01

| Servicio producido | ≈ Particion de referencia | Similitud |
|---|---|---|
| Account Management | account | 1.000 |
| Catalog | catalog | 0.900 |
| Shopping Cart and Order Management | order | 0.917 |

| Clase | En la referencia | De más en | Falta en (referencia) |
|---|---|---|---|
| `CartActionBean` | catalog | Shopping Cart and Order Management (~order) | catalog |

## jpetstore-6 / claude-run1-e4-r02

| Servicio producido | ≈ Particion de referencia | Similitud |
|---|---|---|
| Account Management | account | 0.714 |
| Catalog | catalog | 0.900 |
| Shopping Cart and Order Management | order | 0.688 |

| Clase | En la referencia | De más en | Falta en (referencia) |
|---|---|---|---|
| `Account` | account | Shopping Cart and Order Management (~order) | — |
| `Item` | catalog | Shopping Cart and Order Management (~order) | — |
| `Product` | catalog | Account Management (~account), Shopping Cart and Order Management (~order) | — |
| `CatalogService` | catalog | Account Management (~account), Shopping Cart and Order Management (~order) | — |
| `CartActionBean` | catalog | Shopping Cart and Order Management (~order) | catalog |

## jpetstore-6 / claude-run1-e4-r03

| Servicio producido | ≈ Particion de referencia | Similitud |
|---|---|---|
| Account Management | account | 0.833 |
| Catalog | catalog | 0.900 |
| Shopping Cart and Order Management | order | 0.846 |

| Clase | En la referencia | De más en | Falta en (referencia) |
|---|---|---|---|
| `CatalogService` | catalog | Account Management (~account), Shopping Cart and Order Management (~order) | — |
| `CartActionBean` | catalog | Shopping Cart and Order Management (~order) | catalog |

## jpetstore-6 / claude-run1-e4-r04

| Servicio producido | ≈ Particion de referencia | Similitud |
|---|---|---|
| Account Management | account | 0.833 |
| Catalog | catalog | 0.900 |
| Shopping Cart and Order Management | order | 0.846 |

| Clase | En la referencia | De más en | Falta en (referencia) |
|---|---|---|---|
| `CatalogService` | catalog | Account Management (~account), Shopping Cart and Order Management (~order) | — |
| `CartActionBean` | catalog | Shopping Cart and Order Management (~order) | catalog |

## jpetstore-6 / claude-run1-e4-r05

| Servicio producido | ≈ Particion de referencia | Similitud |
|---|---|---|
| Account Management | account | 1.000 |
| Catalog | catalog | 0.900 |
| Shopping Cart and Order Management | order | 0.917 |

| Clase | En la referencia | De más en | Falta en (referencia) |
|---|---|---|---|
| `CartActionBean` | catalog | Shopping Cart and Order Management (~order) | catalog |

## partsunlimited / claude-run4

| Servicio producido | ≈ Particion de referencia | Similitud |
|---|---|---|
| Catalog | catalog | 1.000 |
| Dealer | dealer | 1.000 |
| Quote | quote | 1.000 |
| Order | order | 1.000 |
| Shipment | shipment | 1.000 |

Sin clases mal asignadas.

Clases `uncounted` (nº de servicios donde quedaron): {'AppInsightsFilter': 5, 'MongoDBProperties': 5, 'OrderingServiceProperties': 5, 'PostgresqlProperties': 5, 'PropertyHelper': 5, 'PingController': 5, 'MongoOperationsWithRetry': 5}

## partsunlimited / claude-run5

| Servicio producido | ≈ Particion de referencia | Similitud |
|---|---|---|
| Product Catalog | catalog | 1.000 |
| Dealer Management | dealer | 1.000 |
| Quote Management | quote | 1.000 |
| Order Management | order | 1.000 |
| Shipment and Delivery | shipment | 0.947 |

| Clase | En la referencia | De más en | Falta en (referencia) |
|---|---|---|---|
| `OrderStatus` | order | Shipment and Delivery (~shipment) | — |

Clases `uncounted` (nº de servicios donde quedaron): {'AppInsightsFilter': 5, 'MongoDBProperties': 5, 'OrderingServiceProperties': 5, 'PostgresqlProperties': 5, 'PropertyHelper': 5, 'PingController': 5, 'MongoOperationsWithRetry': 5}

## partsunlimited / claude-run6

| Servicio producido | ≈ Particion de referencia | Similitud |
|---|---|---|
| Product Catalog | catalog | 1.000 |
| Dealer Management | dealer | 1.000 |
| Quote Management | quote | 1.000 |
| Order Management | order | 1.000 |
| Shipment Management | shipment | 1.000 |

Sin clases mal asignadas.

Clases `uncounted` (nº de servicios donde quedaron): {'AppInsightsFilter': 5, 'MongoDBProperties': 5, 'OrderingServiceProperties': 5, 'PostgresqlProperties': 5, 'PropertyHelper': 5, 'PingController': 5, 'MongoOperationsWithRetry': 5}

## partsunlimited / baseline-run1

| Servicio producido | ≈ Particion de referencia | Similitud |
|---|---|---|
| CatalogService | catalog | 0.857 |
| DealerService | dealer | 0.857 |
| QuoteService | quote | 0.700 |
| OrderService | order | 0.630 |
| ShipmentService | shipment | 0.500 |

| Clase | En la referencia | De más en | Falta en (referencia) |
|---|---|---|---|
| `BadRequestException` | order, quote, shipment | CatalogService (~catalog), DealerService (~dealer) | — |
| `ConflictingRequestException` | order, shipment | CatalogService (~catalog), DealerService (~dealer), QuoteService (~quote) | — |
| `DealerInfo` | dealer | QuoteService (~quote) | — |
| `Order` | order | ShipmentService (~shipment) | — |
| `OrderEventInfo` | order | ShipmentService (~shipment) | — |
| `OrderStatus` | order | ShipmentService (~shipment) | — |
| `OrderUpdateInfo` | order | ShipmentService (~shipment) | — |
| `Quote` | quote | OrderService (~order), ShipmentService (~shipment) | — |
| `QuoteItemInfo` | quote | OrderService (~order), ShipmentService (~shipment) | — |
| `DealersRepository` | dealer | OrderService (~order), QuoteService (~quote), ShipmentService (~shipment) | — |
| `OrderRepository` | order | ShipmentService (~shipment) | — |
| `QuoteRepository` | quote | OrderService (~order), ShipmentService (~shipment) | — |
| `MockDealersRepository` | dealer | OrderService (~order), QuoteService (~quote), ShipmentService (~shipment) | — |
| `MockOrderRepository` | order | ShipmentService (~shipment) | — |
| `MockQuoteRepository` | quote | OrderService (~order), ShipmentService (~shipment) | — |
| `MongoDealersRepository` | dealer | OrderService (~order), QuoteService (~quote), ShipmentService (~shipment) | — |
| `MongoOrderRepository` | order | ShipmentService (~shipment) | — |
| `MongoQuoteRepository` | quote | OrderService (~order), ShipmentService (~shipment) | — |
| `Dealer` | dealer | OrderService (~order), QuoteService (~quote), ShipmentService (~shipment) | — |
| `OrderDetails` | order | ShipmentService (~shipment) | — |
| `QuoteDetails` | quote | OrderService (~order), ShipmentService (~shipment) | — |

Clases `uncounted` (nº de servicios donde quedaron): {'AppInsightsFilter': 5, 'MongoDBProperties': 5, 'OrderingServiceProperties': 5, 'PostgresqlProperties': 5, 'PropertyHelper': 5, 'PingController': 5, 'MongoOperationsWithRetry': 5}

## partsunlimited / baseline-run2

| Servicio producido | ≈ Particion de referencia | Similitud |
|---|---|---|
| CatalogService | catalog | 0.857 |
| DealerService | dealer | 0.857 |
| QuoteService | quote | 0.609 |
| OrderService | order | 0.654 |
| ShipmentService | shipment | 0.514 |

| Clase | En la referencia | De más en | Falta en (referencia) |
|---|---|---|---|
| `BadRequestException` | order, quote, shipment | CatalogService (~catalog), DealerService (~dealer) | — |
| `ConflictingRequestException` | order, shipment | CatalogService (~catalog), DealerService (~dealer), QuoteService (~quote) | — |
| `CatalogItem` | catalog | QuoteService (~quote) | — |
| `DealerInfo` | dealer | QuoteService (~quote) | — |
| `Order` | order | ShipmentService (~shipment) | — |
| `OrderEventInfo` | order | ShipmentService (~shipment) | — |
| `OrderStatus` | order | ShipmentService (~shipment) | — |
| `OrderUpdateInfo` | order | ShipmentService (~shipment) | — |
| `Quote` | quote | OrderService (~order), ShipmentService (~shipment) | — |
| `QuoteItemInfo` | quote | OrderService (~order), ShipmentService (~shipment) | — |
| `CatalogItemsRepository` | catalog | QuoteService (~quote) | — |
| `DealersRepository` | dealer | QuoteService (~quote) | — |
| `OrderRepository` | order | ShipmentService (~shipment) | — |
| `QuoteRepository` | quote | OrderService (~order), ShipmentService (~shipment) | — |
| `MockCatalogItemsRepository` | catalog | QuoteService (~quote) | — |
| `MockDealersRepository` | dealer | OrderService (~order), QuoteService (~quote), ShipmentService (~shipment) | — |
| `MockOrderRepository` | order | ShipmentService (~shipment) | — |
| `MockQuoteRepository` | quote | OrderService (~order), ShipmentService (~shipment) | — |
| `MongoDealersRepository` | dealer | OrderService (~order), QuoteService (~quote), ShipmentService (~shipment) | — |
| `MongoOrderRepository` | order | ShipmentService (~shipment) | — |
| `MongoQuoteRepository` | quote | OrderService (~order), ShipmentService (~shipment) | — |
| `Dealer` | dealer | OrderService (~order), QuoteService (~quote), ShipmentService (~shipment) | — |
| `OrderDetails` | order | ShipmentService (~shipment) | — |
| `QuoteDetails` | quote | OrderService (~order), ShipmentService (~shipment) | — |

Clases `uncounted` (nº de servicios donde quedaron): {'AppInsightsFilter': 5, 'MongoDBProperties': 5, 'OrderingServiceProperties': 5, 'PostgresqlProperties': 5, 'PropertyHelper': 5, 'PingController': 5, 'MongoOperationsWithRetry': 5}

## partsunlimited / baseline-run3

| Servicio producido | ≈ Particion de referencia | Similitud |
|---|---|---|
| CatalogService | catalog | 0.857 |
| DealerService | dealer | 0.857 |
| QuoteService | quote | 0.700 |
| OrderService | order | 0.607 |
| ShipmentService | shipment | 0.486 |

| Clase | En la referencia | De más en | Falta en (referencia) |
|---|---|---|---|
| `BadRequestException` | order, quote, shipment | CatalogService (~catalog), DealerService (~dealer) | — |
| `ConflictingRequestException` | order, shipment | CatalogService (~catalog), DealerService (~dealer), QuoteService (~quote) | — |
| `DealerInfo` | dealer | OrderService (~order), QuoteService (~quote), ShipmentService (~shipment) | — |
| `Order` | order | ShipmentService (~shipment) | — |
| `OrderEventInfo` | order | ShipmentService (~shipment) | — |
| `OrderStatus` | order | ShipmentService (~shipment) | — |
| `OrderUpdateInfo` | order | ShipmentService (~shipment) | — |
| `Quote` | quote | OrderService (~order), ShipmentService (~shipment) | — |
| `QuoteItemInfo` | quote | OrderService (~order), ShipmentService (~shipment) | — |
| `DealersRepository` | dealer | OrderService (~order), QuoteService (~quote), ShipmentService (~shipment) | — |
| `OrderRepository` | order | ShipmentService (~shipment) | — |
| `QuoteRepository` | quote | OrderService (~order), ShipmentService (~shipment) | — |
| `MockDealersRepository` | dealer | OrderService (~order), QuoteService (~quote), ShipmentService (~shipment) | — |
| `MockOrderRepository` | order | ShipmentService (~shipment) | — |
| `MockQuoteRepository` | quote | OrderService (~order), ShipmentService (~shipment) | — |
| `MongoDealersRepository` | dealer | OrderService (~order), QuoteService (~quote), ShipmentService (~shipment) | — |
| `MongoOrderRepository` | order | ShipmentService (~shipment) | — |
| `MongoQuoteRepository` | quote | OrderService (~order), ShipmentService (~shipment) | — |
| `Dealer` | dealer | OrderService (~order), QuoteService (~quote), ShipmentService (~shipment) | — |
| `OrderDetails` | order | ShipmentService (~shipment) | — |
| `QuoteDetails` | quote | OrderService (~order), ShipmentService (~shipment) | — |

Clases `uncounted` (nº de servicios donde quedaron): {'AppInsightsFilter': 5, 'MongoDBProperties': 5, 'OrderingServiceProperties': 5, 'PostgresqlProperties': 5, 'PropertyHelper': 5, 'PingController': 5, 'MongoOperationsWithRetry': 5}

## partsunlimited / claude-run1

| Servicio producido | ≈ Particion de referencia | Similitud |
|---|---|---|
| Product Catalog | catalog | 1.000 |
| Dealer Management | dealer | 1.000 |
| Quote Management | quote | 1.000 |
| Order Management | order | 1.000 |
| Shipment and Delivery | shipment | 1.000 |

Sin clases mal asignadas.

Clases `uncounted` (nº de servicios donde quedaron): {'AppInsightsFilter': 5, 'MongoDBProperties': 5, 'OrderingServiceProperties': 5, 'PostgresqlProperties': 5, 'PropertyHelper': 5, 'PingController': 5, 'MongoOperationsWithRetry': 5}

## partsunlimited / claude-run2

| Servicio producido | ≈ Particion de referencia | Similitud |
|---|---|---|
| Catalog | catalog | 0.923 |
| Dealer | dealer | 0.923 |
| Quote | quote | 1.000 |
| Order | order | 1.000 |
| Shipment | shipment | 1.000 |

| Clase | En la referencia | De más en | Falta en (referencia) |
|---|---|---|---|
| `BadRequestException` | order, quote, shipment | Catalog (~catalog), Dealer (~dealer) | — |

Clases `uncounted` (nº de servicios donde quedaron): {'AppInsightsFilter': 5, 'MongoDBProperties': 5, 'OrderingServiceProperties': 5, 'PostgresqlProperties': 5, 'PropertyHelper': 5, 'PingController': 5, 'MongoOperationsWithRetry': 5}

## partsunlimited / claude-run3

| Servicio producido | ≈ Particion de referencia | Similitud |
|---|---|---|
| Product Catalog | catalog | 1.000 |
| Dealer Management | dealer | 1.000 |
| Quote Management | quote | 1.000 |
| Order Management | order | 1.000 |
| Shipment Management | shipment | 1.000 |

Sin clases mal asignadas.

Clases `uncounted` (nº de servicios donde quedaron): {'AppInsightsFilter': 5, 'MongoDBProperties': 5, 'OrderingServiceProperties': 5, 'PostgresqlProperties': 5, 'PropertyHelper': 5, 'PingController': 5, 'MongoOperationsWithRetry': 5}
