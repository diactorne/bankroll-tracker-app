import pandas as pd
import os
from datetime import datetime
import matplotlib.pyplot as plt
import streamlit as st 
from matplotlib import dates as mdates
import numpy as np

# --- NOUVEAUX IMPORTS POUR GOOGLE SHEETS ---
import gspread 
from google.oauth2.service_account import Credentials 

# --- CONFIGURATION ---
BANKROLL_INIT = 0.00 # Bankroll initiale à 0
# Définition des permissions d'accès (Lecture + Écriture)
SCOPES = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive'] 

# Configuration de la page Streamlit
st.set_page_config(layout="wide", page_title="💰 Suivi de Bankroll - Bet Tracker")

# --- NOUVELLES FONCTIONS DE CONNEXION (HORS CLASSE) ---

@st.cache_resource(ttl=3600) # Cache la connexion pendant 1h pour éviter les appels API abusifs
def connect_to_sheets():
    """Établit la connexion à Google Sheets via le compte de service."""
    
    # 1. Vérifie la présence des secrets Streamlit
    if not st.secrets.get("gcp_service_account") or not st.secrets.get("SHEET_ID"):
        st.error("Les secrets de connexion Google Sheets (gcp_service_account et SHEET_ID) ne sont pas configurés. L'application ne peut pas enregistrer de données de manière persistante.")
        return None

    try:
        # 2. Authentification
        secrets_dict = st.secrets["gcp_service_account"]
        credentials = Credentials.from_service_account_info(secrets_dict, scopes=SCOPES)
        client = gspread.authorize(credentials)
        
        # 3. Ouverture de la feuille de calcul
        sheet_id = st.secrets["SHEET_ID"]
        spreadsheet = client.open_by_key(sheet_id)
        
        # Retourne la première feuille (Worksheet)
        return spreadsheet.sheet1
        
    except Exception as e:
        # Si une erreur se produit (mauvaise clé, ID de feuille incorrect), l'application s'arrête
        st.error(f"Erreur fatale de connexion à Google Sheets : {e}. Vérifiez vos secrets et les permissions d'accès ('Éditeur') de l'email de service.")
        return None


@st.cache_resource
def load_tracker():
    """Charge le tracker et le met en cache pour qu'il ne soit chargé qu'une seule fois."""
    return BankrollTracker(solde_initial=BANKROLL_INIT)

# --- CLASSE DE LOGIQUE (BankrollTracker) ---

class BankrollTracker:
    
    def __init__(self, solde_initial):
        self.solde_initial = solde_initial
        self._charger_ou_initialiser_df() 
        
        if not self.df.empty:
            self.bankroll_actuelle = self.df['Bankroll_Finale'].iloc[-1]
        else:
            self.bankroll_actuelle = solde_initial

    def _charger_ou_initialiser_df(self):
        """Charge le DataFrame depuis Google Sheets ou crée une ligne initiale."""
        
        self.df = pd.DataFrame() 
        COLONNES_ATTENDUES = [
            'Date', 'Type', 'Montant_Pari', 'Cote', 'Résultat', 
            'Gain_Net', 'Bankroll_Finale', 'Details_Pari' 
        ]

        try:
            sheet = connect_to_sheets()
            
            if sheet:
                # Lire toutes les données. head=1 utilise la première ligne comme en-tête.
                data = sheet.get_all_records(head=1)
                df_temp = pd.DataFrame(data)
                
                if not df_temp.empty and all(col in df_temp.columns for col in COLONNES_ATTENDUES):
                    
                    self.df = df_temp[COLONNES_ATTENDUES].copy()
                    
                    # Conversion des colonnes numériques
                    for col in ['Montant_Pari', 'Cote', 'Gain_Net', 'Bankroll_Finale']:
                        # Coerce pour gérer les valeurs non numériques (comme N/A ou vides)
                        self.df[col] = pd.to_numeric(self.df[col], errors='coerce').fillna(0.0) 
                        
                else:
                    self._creer_df_initial()
            else:
                self.df = pd.DataFrame(columns=COLONNES_ATTENDUES)
                self._creer_df_initial() # Initialise en cas d'échec de connexion

        except Exception as e:
            st.error(f"Une erreur s'est produite lors de la lecture des données Sheets. Utilisation du DF initial. Détail: {e}")
            self.df = pd.DataFrame(columns=COLONNES_ATTENDUES)
            self._creer_df_initial() 

        # S'assurer que la première ligne est la ligne DEBUT
        if self.df.empty or self.df.iloc[0]['Type'] != 'DEBUT':
             self._creer_df_initial() 
             
        # Recalculer l'historique après chargement pour garantir l'exactitude des totaux
        self.calculer_bankroll_historique(self.solde_initial)

    def _creer_df_initial(self):
        """Crée un DataFrame vierge avec la ligne d'initialisation."""
        self.df = pd.DataFrame(columns=[
            'Date', 'Type', 'Montant_Pari', 'Cote', 'Résultat', 
            'Gain_Net', 'Bankroll_Finale', 'Details_Pari' 
        ])
        self.df.loc[0] = [
            datetime.now().strftime('%Y-%m-%d'), 
            'DEBUT', 0.0, 0.0, 'N/A', 0.0, self.solde_initial, 'N/A'
        ]


    def calculer_bankroll_historique(self, solde_initial):
        """Recalcule la colonne Bankroll_Finale en cas de besoin."""
        
        if self.df.empty:
            return

        idx_debut = self.df[self.df['Type'] == 'DEBUT'].index
        
        if not idx_debut.empty:
            start_solde = self.df.loc[idx_debut[0], 'Bankroll_Finale']
            
            self.df['Gain_Net_Cumule'] = self.df['Gain_Net'].cumsum()
            self.df['Bankroll_Finale'] = start_solde + self.df['Gain_Net_Cumule']
            self.df.drop(columns=['Gain_Net_Cumule'], inplace=True, errors='ignore') # errors='ignore' pour éviter l'erreur si la colonne n'existe pas

            self.bankroll_actuelle = self.df['Bankroll_Finale'].iloc[-1]
        else:
            self.df['Bankroll_Finale'] = solde_initial + self.df['Gain_Net'].cumsum()
            self.bankroll_actuelle = self.df['Bankroll_Finale'].iloc[-1]


    def _sauvegarder(self):
        """Sauvegarde le DataFrame entier dans Google Sheets."""
        sheet = connect_to_sheets()
        if sheet:
            # Conversion du DataFrame en liste de listes (y compris les en-têtes)
            data_to_write = [self.df.columns.values.tolist()] + self.df.values.tolist()
            
            # Écrit les données dans la feuille (écrase le contenu existant)
            # Utilisation de 'USER_ENTERED' pour que Sheets interprète les nombres comme des nombres
            sheet.clear()
            sheet.update(data_to_write, value_input_option='USER_ENTERED')
            return True
        return False

    def ajouter_pari(self, date_str, montant_pari, cote, resultat, details_pari="Général"): 
        """Ajoute une nouvelle transaction de type 'Pari'."""
        
        if resultat not in ['Gagné', 'Perdu', 'Annulé']:
            return "Erreur: Le résultat doit être 'Gagné', 'Perdu' ou 'Annulé'."

        if resultat == 'Gagné':
            gain_net = (montant_pari * cote) - montant_pari
        elif resultat == 'Perdu':
            gain_net = -montant_pari
        else:
            gain_net = 0.0

        nouvelle_bankroll = self.bankroll_actuelle + gain_net

        nouvelle_entree = pd.Series({
            'Date': date_str, 'Type': 'Pari', 'Montant_Pari': montant_pari, 
            'Cote': cote, 'Résultat': resultat, 'Gain_Net': gain_net, 
            'Bankroll_Finale': nouvelle_bankroll, 'Details_Pari': details_pari
        })

        self.df.loc[len(self.df)] = nouvelle_entree
        self.bankroll_actuelle = nouvelle_bankroll
        return self._sauvegarder()

    def ajouter_fonds(self, montant, type_operation='DEPOT'):
        """Ajoute une transaction de dépôt ou de retrait."""
        
        if type_operation not in ['DEPOT', 'RETRAIT']:
            return "Erreur: Le type doit être 'DEPOT' ou 'RETRAIT'."

        gain_net = montant if type_operation == 'DEPOT' else -montant
        nouvelle_bankroll = self.bankroll_actuelle + gain_net

        nouvelle_entree = pd.Series({
            'Date': datetime.now().strftime('%Y-%m-%d'), 'Type': type_operation, 
            'Montant_Pari': 0.0, 'Cote': 0.0, 'Résultat': 'N/A', 'Gain_Net': gain_net, 
            'Bankroll_Finale': nouvelle_bankroll, 'Details_Pari': 'N/A'
        })
        
        self.df.loc[len(self.df)] = nouvelle_entree
        self.bankroll_actuelle = nouvelle_bankroll
        return self._sauvegarder()
    
    # ... (le reste de la classe et des fonctions utilitaires sont inchangés) ...
    # Le reste du code (calculer_statistiques, creer_figure_graphique, display_stats, add_pari, main) 
    # n'a pas besoin de modifications majeures, car il utilise les méthodes de la classe que nous avons mises à jour.

# --- FONCTIONS UTILITAIRES STREAMLIT ---
# @st.cache_resource def load_tracker(): est au-dessus

def display_stats(tracker):
    """Affiche les statistiques dans la colonne de visualisation."""
    stats = tracker.calculer_statistiques()
    
    st.markdown("### 📊 Statistiques Actuelles")
    
    if stats:
        col_s1, col_s2, col_s3 = st.columns(3)
        col_s1.metric("Solde Actuel", stats['Solde Actuel'])
        col_s2.metric("Profit Net (paris)", stats['Profit Net (paris)'])
        col_s3.metric("ROI", stats['ROI'])
        
        col_s4, col_s5, col_s6 = st.columns(3)
        col_s4.metric("Total des Paris", stats['Total des Paris'])
        col_s5.metric("Total Misé", stats['Total Misé'])
        col_s6.metric("Taux de Réussite", stats['Taux de Réussite'])

    else:
        st.info(f"Bankroll Actuelle: {tracker.bankroll_actuelle:.2f} € - Effectuez un dépôt ou ajoutez un premier pari!")

def add_pari(tracker, form_data):
    """Gère l'ajout d'un pari depuis le formulaire."""
    try:
        date_str = form_data['date']
        montant = float(form_data['montant'])
        cote = float(form_data['cote'])
        details_pari = form_data['details_pari']
        resultat = form_data['resultat']
        
        datetime.strptime(date_str, '%Y-%m-%d')
        
        if montant <= 0 or cote < 1.0:
            st.error("Montant ou cote invalide (doivent être positifs et cote >= 1.0).")
            return

        if tracker.ajouter_pari(date_str, montant, cote, resultat, details_pari):
            st.success("Pari enregistré avec succès ! L'application se rafraîchit...")
            st.cache_resource.clear() # IMPORTANT: Vide le cache pour forcer la relecture des données Sheets
            st.experimental_rerun()
        else:
            st.error("Erreur de sauvegarde. Vérifiez votre connexion à Google Sheets.")


    except ValueError as e:
        st.error(f"Erreur de saisie : Veuillez vérifier les formats. Détail: {e}")
    except Exception as e:
        st.error(f"Une erreur inattendue est survenue: {e}")

# --- DISPOSITION PRINCIPALE DE L'APPLICATION STREAMLIT ---

def main():
    """Fonction principale Streamlit."""
    
    tracker = load_tracker()

    st.title("💰 Suivi de Bankroll - Bet Tracker")
    
    col_controle, col_visualisation = st.columns([1, 2])

    # --- COLONNE DE CONTRÔLE (FORMULAIRES) ---
    with col_controle:
        st.header("Opérations")
        
        # Formulaire d'ajout de Pari
        with st.form("form_pari", clear_on_submit=True):
            st.subheader("Ajouter un Pari")
            
            date_pari = st.date_input("Date du Pari", datetime.now(), format="YYYY-MM-DD").strftime('%Y-%m-%d')
            montant = st.number_input("Montant Parié (€)", min_value=0.01, format="%.2f", step=1.0)
            cote = st.number_input("Cote", min_value=1.00, format="%.2f", step=0.01)
            
            details_pari = st.text_input("Détails du pari", value="Général") 
            
            resultat = st.selectbox("Résultat", ['Gagné', 'Perdu', 'Annulé'])

            submitted = st.form_submit_button("Enregistrer Pari")
            
            if submitted:
                form_data = {
                    'date': date_pari, 'montant': montant, 'cote': cote,
                    'details_pari': details_pari, 
                    'resultat': resultat
                }
                add_pari(tracker, form_data)

        st.markdown("---")
        
        # Formulaire d'ajout/retrait de Fonds
        with st.form("form_fonds", clear_on_submit=True):
            st.subheader("Dépôt / Retrait")
            
            montant_fonds = st.number_input("Montant (€)", min_value=0.01, format="%.2f", step=1.0)
            type_operation = st.radio("Type d'opération", ('DEPOT', 'RETRAIT'))
            
            submitted_fonds = st.form_submit_button(f"{'Ajouter' if type_operation == 'DEPOT' else 'Retirer'} Fonds")
            
            if submitted_fonds:
                if tracker.ajouter_fonds(montant_fonds, type_operation):
                    st.success(f"{type_operation} enregistré avec succès ! L'application se rafraîchit...")
                    st.cache_resource.clear()
                    st.experimental_rerun()
                else:
                    st.error("Erreur lors de l'opération de fonds.")


    # --- COLONNE DE VISUALISATION (STATS & GRAPHIQUE) ---
    with col_visualisation:
        display_stats(tracker)

        st.markdown("---")
        
        st.pyplot(tracker.creer_figure_graphique())
        
        st.markdown("### Historique des Transactions")
        
        # Affichage du DataFrame avec la colonne renommée pour l'utilisateur
        df_affichage = tracker.df.rename(columns={'Details_Pari': 'Détails du pari'})
        
        st.dataframe(df_affichage.tail(10), use_container_width=True)


if __name__ == '__main__':
    main()









