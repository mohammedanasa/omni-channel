## 🛍️ Omnichannel POS & Order Management Hub

A unified, multi-tenant platform designed to manage traditional in-store **Point of Sale (POS)** operations and aggregate orders from multiple online channels (eg: UberEats, DoorDash, etc.). The system is built on a scalable **Django** backend, ensuring data isolation, real-time updates, and high transactional integrity.

## 🌟 Key Features

* **Multi-Tenant Architecture:** Isolates each **Merchant** (Tenant) into its own Postgres schema for maximum security and data integrity (`django-tenants`).
* **Unified Order Management (OMS):** Standardizes incoming orders from all sources (In-store POS, Webhooks) into a single `UnifiedOrder` model.
* **Location Scoping:** Enforces strict permission boundaries so staff/managers at one physical **Location** cannot access data from another within the same Merchant.
* **Real-Time KDS:** Utilizes **WebSockets (Django Channels)** to push new orders and status updates instantly to Kitchen Display Screens (KDS).
* **Aggregator Hub:** Dedicated webhook receiver and adapter logic to normalize payloads from third-party delivery platforms (UberEats, etc.).
* **Role-Based Access Control (RBAC):** Granular permissions for Owners, Managers, and Cashiers, including **PIN override logic** for sensitive actions (voids, refunds).

***

## 🏗️ Architecture Overview

The system uses a **Hybrid Cloud Model**, where the core logic and data are centralized (Cloud), but local clients handle the transactional interface and hardware.

### High-Level Architecture
The **Django Backend** acts as the central traffic controller, integrating three major systems: the traditional POS, the OMS, and the Aggregator Hub. 

### Core Data Model
The database uses a single, unified structure for all transactions across channels.
The `UnifiedOrder` entity is central, linked to `Product` and specific `Location` data. 

[Image of database schema for order management system]


### Webhook Flow (Aggregation)
External payloads are received by a public DRF endpoint, routed to the correct Tenant schema, and normalized via an **Adapter Pattern** before being saved as a `UnifiedOrder`. 

[Image of webhook processing flow diagram]


***

## 🛠️ Technology Stack

| Component | Technology | Role |
| :--- | :--- | :--- |
| **Backend Framework** | **Django** & Python 3.11+ | Core logic and ORM. |
| **API** | **Django REST Framework (DRF)** | API access, security, and serialization. |
| **Database** | **PostgreSQL** | Robust transactional integrity and multi-tenancy (`django-tenants`). |
| **Real-Time** | **Django Channels** & Redis | WebSocket server for Kitchen Display and order updates. |
| **Background Tasks** | **Celery** & Redis | Asynchronous inventory sync and reporting. |
| **Multi-Tenancy** | **django-tenants** | Schema isolation between merchants. |
| **Permissions** | **django-rules** | Fast, logic-based access control. |
| **Frontend/POS** | *React/Vue (Client)* | PWA/Web-based POS and KDS clients. |

***

## 🚀 Local Setup & Installation

### Prerequisites

* Python 3.11+
* PostgreSQL
* Redis (for Channels and Celery)

### 1. Clone the Repository

```bash
git clone https://github.com/mohammedanasa/omni-channel-multi-tenant-pos-oms
cd omnichannel-pos-hub