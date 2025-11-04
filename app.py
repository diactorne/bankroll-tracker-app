import pandas as pd
import os
from datetime import datetime
import matplotlib.pyplot as plt
import streamlit as st # Import de Streamlit
from matplotlib import dates as mdates

# --- CONFIGURATION ---
FICHIER_DATA = 'bankroll_data.csv'
BANKROLL_INIT = 1000.00

# Configuration de la page Streamlit
st.set_page_config(layout="wide", page_title="💰 Suivi de Bankroll - Bet Tracker")

# --- CLASSE DE LOGIQUE (BankrollTracker) ---

class BankrollTracker:
    # La logique interne reste globalement la même pour la gestion des données
    
    def __init__(self, solde_initial):
        self.solde_initial = solde_initial
        # L'initialisation doit être dans la session Streamlit pour la persistance
        self._charger_ou_initialiser_df() 
        
        if not self.df.empty:
            self.bankroll_actuelle = self.df['Bankroll_Finale'].iloc[-1]
        else:
            self.bankroll_actuelle = solde_initial

    def _charger_ou_initialiser_df(self):
        """Charge le DataFrame existant ou en crée un nouveau."""
        self.df = pd.DataFrame() 

        if os.path.exists(FICHIER_DATA):
            try:
                df_temp = pd.read_csv(FICHIER_DATA, parse_dates=['Date'], encoding='utf-8')
                if not df_temp.empty:
                    self.df = df_temp
                else:
                    self._creer_df_initial()
            except pd.errors.EmptyDataError:
                self._creer_df_initial()
        else:
            self._creer_df_initial()
        
        if self.df.empty or self.df.iloc[0]['Type'] != 'DEBUT':
             self._creer_df_initial() 
             
        self.calculer_bankroll_historique(self.solde_initial)

    def _creer_df_initial(self):
        """Crée un DataFrame vierge avec la ligne d'initialisation."""
        self.df = pd.DataFrame(columns=[
            'Date', 'Type', 'Montant_Pari', 'Cote', 'Résultat', 
            'Gain_Net', 'Bankroll_Finale', 'Sport'
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
            self.df.drop(columns=['Gain_Net_Cumule'], inplace=True)

            self.bankroll_actuelle = self.df['Bankroll_Finale'].iloc[-1]
        else:
            self.df['Bankroll_Finale'] = solde_initial + self.df['Gain_Net'].cumsum()
            self.bankroll_actuelle = self.df['Bankroll_Finale'].iloc[-1]


    def _sauvegarder(self):
        """Sauvegarde le DataFrame dans un fichier CSV."""
        self.df.to_csv(FICHIER_DATA, index=False)

    def ajouter_pari(self, date_str, montant_pari, cote, resultat, sport="Général"):
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
            'Bankroll_Finale': nouvelle_bankroll, 'Sport': sport
        })

        self.df.loc[len(self.df)] = nouvelle_entree
        self.bankroll_actuelle = nouvelle_bankroll
        self._sauvegarder()
        return True # Succès

    def ajouter_fonds(self, montant, type_operation='DEPOT'):
        """Ajoute une transaction de dépôt ou de retrait."""
        
        if type_operation not in ['DEPOT', 'RETRAIT']:
            return "Erreur: Le type doit être 'DEPOT' ou 'RETRAIT'."

        gain_net = montant if type_operation == 'DEPOT' else -montant
        nouvelle_bankroll = self.bankroll_actuelle + gain_net

        nouvelle_entree = pd.Series({
            'Date': datetime.now().strftime('%Y-%m-%d'), 'Type': type_operation, 
            'Montant_Pari': 0.0, 'Cote': 0.0, 'Résultat': 'N/A', 'Gain_Net': gain_net, 
            'Bankroll_Finale': nouvelle_bankroll, 'Sport': 'N/A'
        })
        
        self.df.loc[len(self.df)] = nouvelle_entree
        self.bankroll_actuelle = nouvelle_bankroll
        self._sauvegarder()
        return True
    
    def calculer_statistiques(self):
        """Calcule les statistiques clés de la bankroll et les retourne."""
        paris_df = self.df[self.df['Type'] == 'Pari'].copy()

        if paris_df.empty:
            return None

        total_paris = len(paris_df)
        total_mises = paris_df['Montant_Pari'].sum()
        profit_total = paris_df['Gain_Net'].sum()
        
        roi_pour_paris = (profit_total / total_mises) * 100 if total_mises > 0 else 0.0

        paris_gagnes = len(paris_df[paris_df['Résultat'] == 'Gagné'])
        taux_reussite = (paris_gagnes / total_paris) * 100

        stats = {
            "Solde Actuel": f"{self.bankroll_actuelle:.2f} €",
            "Profit Net (paris)": f"{profit_total:.2f} €",
            "Total des Paris": total_paris,
            "Total Misé": f"{total_mises:.2f} €",
            "ROI": f"{roi_pour_paris:.2f} %",
            "Taux de Réussite": f"{taux_reussite:.2f} %"
        }
        return stats

    def creer_figure_graphique(self):
        """
        Crée la figure Matplotlib pour le graphique d'évolution.
        """
        
        fig, ax = plt.subplots(figsize=(8, 4))
        
        df_plot = self.df.copy()
        df_plot['Date'] = pd.to_datetime(df_plot['Date']) 
        
        daily_bankroll = df_plot.set_index('Date')['Bankroll_Finale'].resample('D').last().ffill()
        
        if not daily_bankroll.empty:
            ax.plot(daily_bankroll.index, daily_bankroll.values, marker='o', linestyle='-', color='blue', label='Bankroll')
            ax.set_title('Évolution Quotidienne de la Bankroll', fontsize=14)
            ax.set_xlabel('Date', fontsize=10)
            ax.set_ylabel('Solde (€)', fontsize=10)
            ax.grid(True, linestyle='--', alpha=0.6)
            
            # Correction de l'affichage des dates
            date_fmt = mdates.DateFormatter('%d-%m') 
            ax.xaxis.set_major_formatter(date_fmt)
            locator = mdates.AutoDateLocator()
            ax.xaxis.set_major_locator(locator)
            fig.autofmt_xdate(rotation=45)
            
        else:
             ax.text(0.5, 0.5, "Pas de données pour le graphique d'évolution.", 
                     horizontalalignment='center', verticalalignment='center', transform=ax.transAxes)

        return fig

# --- FONCTIONS UTILITAIRES STREAMLIT ---

@st.cache_resource
def load_tracker():
    """Charge le tracker et le met en cache pour qu'il ne soit chargé qu'une seule fois."""
    return BankrollTracker(solde_initial=BANKROLL_INIT)

def display_stats(tracker):
    """Affiche les statistiques dans la colonne de visualisation."""
    stats = tracker.calculer_statistiques()
    
    st.markdown("### 📊 Statistiques Actuelles")
    
    if stats:
        # Affichage en deux colonnes pour être plus compact
        col_s1, col_s2, col_s3 = st.columns(3)
        col_s1.metric("Solde Actuel", stats['Solde Actuel'])
        col_s2.metric("Profit Net (paris)", stats['Profit Net (paris)'])
        col_s3.metric("ROI", stats['ROI'])
        
        col_s4, col_s5, col_s6 = st.columns(3)
        col_s4.metric("Total des Paris", stats['Total des Paris'])
        col_s5.metric("Total Misé", stats['Total Misé'])
        col_s6.metric("Taux de Réussite", stats['Taux de Réussite'])

    else:
        st.info(f"Bankroll Actuelle: {tracker.bankroll_actuelle:.2f} € - Ajoutez un premier pari!")

def add_pari(tracker, form_data):
    """Gère l'ajout d'un pari depuis le formulaire."""
    try:
        date_str = form_data['date']
        montant = float(form_data['montant'])
        cote = float(form_data['cote'])
        sport = form_data['sport']
        resultat = form_data['resultat']
        
        datetime.strptime(date_str, '%Y-%m-%d')
        
        if montant <= 0 or cote < 1.0:
            st.error("Montant ou cote invalide (doivent être positifs et cote >= 1.0).")
            return

        tracker.ajouter_pari(date_str, montant, cote, resultat, sport)
        st.success("Pari enregistré avec succès ! L'application se rafraîchit...")
        
        # Streamlit a besoin d'être relancé pour mettre à jour les colonnes/graphiques
        st.experimental_rerun() 

    except ValueError as e:
        st.error(f"Erreur de saisie : Veuillez vérifier les formats. Détail: {e}")
    except Exception as e:
        st.error(f"Une erreur inattendue est survenue: {e}")

# --- DISPOSITION PRINCIPALE DE L'APPLICATION STREAMLIT ---

def main():
    """Fonction principale Streamlit."""
    
    # Utilisation du cache pour éviter de recharger le CSV à chaque interaction
    tracker = load_tracker()

    st.title("💰 Suivi de Bankroll - Bet Tracker")
    
    # Division de l'interface en deux colonnes
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
            sport = st.text_input("Sport", value="Général")
            resultat = st.selectbox("Résultat", ['Gagné', 'Perdu', 'Annulé'])

            submitted = st.form_submit_button("Enregistrer Pari")
            
            if submitted:
                form_data = {
                    'date': date_pari, 'montant': montant, 'cote': cote,
                    'sport': sport, 'resultat': resultat
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
                    st.experimental_rerun()
                else:
                    st.error("Erreur lors de l'opération de fonds.")


    # --- COLONNE DE VISUALISATION (STATS & GRAPHIQUE) ---
    with col_visualisation:
        display_stats(tracker)

        st.markdown("---")
        
        st.pyplot(tracker.creer_figure_graphique())
        
        st.markdown("### Historique des Transactions")
        st.dataframe(tracker.df.tail(10), use_container_width=True)


if __name__ == '__main__':

    main()
