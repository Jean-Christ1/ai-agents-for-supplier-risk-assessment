==>  Les agents d'IA pour l'évaluation des risques fournisseurs

- Date : 9 février 2026

- Participants :
    • Chef de projet (Antoine BIJEIRE)
    • Armand K. AMOUSSOU
        ○ ==> Mentions : 
            § Franck ARCHER (VIP),  
            § Alexey GUERASSIMOV (expert technique agentique), 
            § CHESNE Fabien (cadrage métier)

- Problématique client (Manitou Group)
    • Manitou Group, industriel basé à l'ouest de la France fabriquant des chariots élévateurs (similaire à Caterpillar/engins de chantier), subit les dysfonctionnements de ses fournisseurs en matières premières (métaux, roues, électronique, etc.) qui sont parfois dus à des facteurs exogènes, tels que les actualités pertinentes, les événements météorologiques, situations politiques, des accident, et d’autres informations publiques faisant référence aux fournisseurs. Ces événements peuvent apparaître dans des informations d’actualité provenant de différentes sources et à des moments qui ne sont pas toujours synchronisés partout.
    • Actuellement en mode réactif : retards, défauts de livraison impactent directement la production. Ils disposent de données internes partielles (scoring financier basique via 3 critères "??? À demander"), mais à des difficulté d'anticipation proactive des risques fournisseurs. 
    • Besoin : Besoin urgent d'un système enrichi (un 4e critère scoring grâce au information exogène) pour piloter la supply chain via IA générative.​
- Objectif métier : Anticipation du risque fournisseur (c'est en fait de l'évaluation des risques des fournisseurs)
        ○ But : 
            § Atténuer les risques liés aux fournisseurs
            § Avoir la capacité de mieux gérer les relations avec les fournisseurs et d’améliorer les stratégies d’approvisionnement.

- Objectifs du projet
    • Automatiser et industrialiser les 3 critères existants (analytiques/statistiques classiques, issus de BigQuery, suivis manuels/Excel).
    • Ajouter un 4e critère innovant via IA générative/agentique : transformer textes/news (ex. Google News, Les Échos, Moody's alternatif) en score risque numérisé (0-100), ex. géopolitique (instabilités Chine), environnemental, etc.

- MVP (Minimum Viable Product) : 
    • Par exemple, 10-20 fournisseurs prioritaires, alimentation quotidienne (batch à froid, non temps réel), scoring global pondéré (ex. finance 50%, autres variables).
    • Livrables finaux : Base BigQuery réconciliée + dashboard Looker (scoring global + 4 critères par fournisseur/mois) en production GCP.​

- Architecture technique proposée (stack GCP) :
    • Système agentique réduit : Orchestrateur light (préparé pour scalabilité) + 1 agent "Cruncher" (analyse/synthèse textes → score risque via LLM/RAG/vectorisation).
    • Flux quotidien : Collecte auto données (internes + externes), agrégation/analyse, scoring enrichi.
    • Sources à cadrer :
        ○ Peut-être avec ou pas Google News (trop varié) ; 
        ○ À valider avec client (si des abonnements dédiés ?). Framework interne Python d'Alexey ou Google ADK (open source comme LangChain à discuter).
        
        
- Hors scope budget : Agent RAG conversationnel (interrogation docs) ; extension à tous fournisseurs.




Pourquoi ces acteurs de la Supply Chaine tournent ils vers l'approche Gen AI (au sens de LLM) :  En effet, pour obtenir des informations pour évaluer et réduire les risques liés aux fournisseurs, ces organisations (acteurs de la Supply Chaine) doivent améliorer leur capacité à collecter et traiter des données provenant de nombreuses sources. Mais, étant donné qu’environ 60 % à 70 % du temps d’un analyste est consacré à la collecte de données, ajouter davantage d’éléments de données (comme les source de journalistique de diverses horizons) à sa charge de travail déjà croissante peut sembler irréaliste. C’est l’une des raisons pour lesquelles les responsables de la chaîne d’approvisionnement se tournent de plus en plus vers l’IA.


