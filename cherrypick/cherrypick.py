__author__ = "Lucas Carames"
__license__="MIT"
__version__='0.1.0'
__maintainer__='Lucas Carames'
__email__='lgpcarames@gmail.com'


import pandas as pd
import numpy as np
import lightgbm as lgb
import optuna
from tqdm import tqdm

from sklearn.model_selection import StratifiedKFold
from functools import reduce
from typing import Union, Any


from sklearn.metrics import roc_auc_score, roc_curve, confusion_matrix
from sklearn.linear_model import LogisticRegression
from sklearn.tree import DecisionTreeClassifier
from sklearn.ensemble import RandomForestClassifier
from sklearn.feature_selection import mutual_info_classif
from sklearn.dummy import DummyClassifier
from sklearn.preprocessing import MinMaxScaler

from sklearn.cluster import KMeans

import shap

import warnings

warnings.filterwarnings('ignore')
# Categorical features process
class CatEncoder:
    """
    Similarly to SKLearn LabelEncoder, but it does work with new categories.

    To be use:
    ----------
    ce = CatEncoder()
    ce.fit(dataframe[selected_columns])

    ce.transform(dataframe[selected_columns])
    

    Developed by: Vinícius Ormenesse - https://github.com/ormenesse
    """

    def __init__(self) -> None:
        """
        Construtor da classe
        """
        self.dic = {}
        self.rev_dic = {}

    def fit(self, vet: Union[pd.Series, list]) -> None:
        """
        Prepara o encoder para os dados passados na variável vet.
        """
        uniques = []
        for c in vet.unique():
            if str(type(c)) == "<class 'str'>":
                uniques.append(c)
        uniques.sort()
        for a, b in enumerate(uniques):
            self.dic[b] = a
            self.rev_dic[a] = b
        return self
    def check(
            self,
            vet: Union[ pd.Series, list]
            ) -> pd.Series:
        """
        Checa o tipo da variável vet. Transformando em pd.Series, caso seja do tipo list.
        """
        try:
            if type(vet) == list:
                return pd.Series(vet)
            return vet
        except Exception:
            return vet
    def transform(self, vet: pd.DataFrame) -> pd.Series:
        """
        Realiza a transformação do label de acordo com o que foi adaptado pelo encoder.
        """
        vet = self.check(vet)
        return vet.map(self.dic)
    
    def inverse_transform(self, vet: pd.Series) -> pd.Series:
        """
        Inverte a transformação realizada pelo encoder.
        """
        vet = self.check(vet)
        return vet.map(self.rev_dic)
    
    def fit_transform(self, vet: pd.Series) -> pd.Series:
        """
        Adapta o encoder aos dados e em seguida os transforma.
        """
        vet = self.check(vet)
        self.fit(vet.astype(str))
        return self.transform(vet.astype(str))
    

class SearchHyperParams:
    def __init__(self, cross_val=5):
        # Loading model variables
        self.lgbm_model = None
        self.lr_model = None
        self.decision_tree_model = None

        # Loading dataframe, variables and target
        self.cross_val = cross_val


    def objective_lr(
                    self,
                    trial: Any,
                    var_train: Union[list, pd.Series, pd.DataFrame],
                    var_test: Union[list, pd.Series, pd.DataFrame]
                    ) -> tuple:
        param_grid = {
            "tol": trial.suggest_float("tol", 0.000001, 1.0),
            "max_iter": trial.suggest_int("max_iter", 10, 200),
            "l1_ratio": trial.suggest_float("l1_ratio", 0.00001, 1.0)
        }

        cv = StratifiedKFold(n_splits=self.cross_val, shuffle=True, random_state=13)

        cv_scores = np.empty(self.cross_val)
        cv_scores_train = np.empty(self.cross_val)

        for idx, (train_idx, test_idx) in enumerate(cv.split(var_train, var_test)):
            X_train, X_test = var_train.iloc[train_idx], var_train.iloc[test_idx]
            y_train, y_test = var_test.iloc[train_idx], var_test[test_idx]


            model = LogisticRegression(class_weight = 'balanced',
                                        penalty='elasticnet',
                                        solver='saga',
                                        random_state=13,
                                        **param_grid)

            model.fit(
                X_train,
                y_train
            )

            preds = model.predict_proba(X_test)

            try:
                cv_scores[idx] = roc_auc_score(y_test, preds[:, 1])
                cv_scores_train[idx] = roc_auc_score(y_train, model.predict_proba(X_train)[:, 1]) - cv_scores[idx]
            except Exception:
                cv_scores[idx] = -1
                cv_scores_train[idx] = 1
        return np.mean(cv_scores), np.mean(cv_scores_train)


    def objective_decision_tree(
                                self,
                                trial: Any,
                                var_train: Union[list, pd.Series, pd.DataFrame],
                                var_test: Union[list, pd.Series, pd.DataFrame]
                                ) -> tuple:
        """
        Função de estudo do optuna adaptada para Árvore de Decisão.
        Paramêtros
        ----------
        trial: Função processo de avaliação optuna
        x: Variáveis Explicativa
        y: Nome da variável alvo.
        Retorna
        -------
        tuple -> roc-auc média do modelo base de dados de teste, diferença da roc-auc de teste e
        do treinamento. 
        """
        param_grid = {
            "criterion": trial.suggest_categorical("criterion", ['gini', 'entropy']),
            "splitter": trial.suggest_categorical("splitter", ['random', 'best']),
            "min_samples_leaf": trial.suggest_int('min_samples_leaf', 1, 30),
            'min_samples_split': trial.suggest_int('min_samples_split', 2, 30),
            'max_leaf_nodes': trial.suggest_int('max_leaf_nodes', 5, 40),
            'ccp_alpha': trial.suggest_float('ccp_alpha', 0.0001, 0.05),
            'max_depth': trial.suggest_int('max_depth', 2, 50)

            
        }

        cv = StratifiedKFold(n_splits=self.cross_val, shuffle=True, random_state=42)

        cv_scores = np.empty(self.cross_val)
        cv_scores_train = np.empty(self.cross_val)
        for idx, (train_idx, test_idx) in enumerate(cv.split(var_train, var_test)):
            X_train, X_test = var_train.iloc[train_idx], var_train.iloc[test_idx]
            y_train, y_test = var_test[train_idx], var_test[test_idx]

            model = DecisionTreeClassifier(
                **param_grid
            )

            model.fit(
                X_train,
                y_train
            )

            preds = model.predict_proba(X_test)
            cv_scores[idx] = roc_auc_score(y_test, preds[:,1])
            cv_scores_train[idx] = roc_auc_score(y_train,model.predict_proba(X_train)[:,1]) - cv_scores[idx]
            
        return np.mean(cv_scores), np.mean(cv_scores_train)
        

    def objective_lgb(self,
                      trial: Any,
                      var_train: Union[list, pd.Series, pd.DataFrame],
                      var_test: Union[list, pd.Series, pd.DataFrame]
                      ) -> tuple:
        param_grid = {
            # "device_type": trial.suggest_categorical("device_type", ['gpu']),
            "n_estimators": trial.suggest_int("n_estimators", 5,50),
            "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.2),
            "num_leaves": trial.suggest_categorical("num_leaves", [2,5,10,31]),
            "max_depth": trial.suggest_categorical("max_depth", [2,3,5]),
            "reg_alpha": trial.suggest_float("lambda_l1", 0, 1),
            "reg_lambda": trial.suggest_float("lambda_l2", 0, 1),
            "colsample_bytree": trial.suggest_float("colsample_bytree",  0.05, 1)
        }

        cv = StratifiedKFold(n_splits=self.cross_val, shuffle=True, random_state=42)

        cv_scores = np.empty(self.cross_val)
        cv_scores_train = np.empty(self.cross_val)
        for idx, (train_idx, test_idx) in enumerate(cv.split(var_train, var_test)):
            X_train, X_test = var_train.iloc[train_idx], var_train.iloc[test_idx]
            y_train, y_test = var_test[train_idx], var_test[test_idx]
            model = lgb.LGBMClassifier(objective="binary", **param_grid)
            model.fit(
                X_train,
                y_train,
                eval_set=[(X_test, y_test)],
                eval_metric="auc",
                early_stopping_rounds=100,
                verbose=False
            )
            preds = model.predict_proba(X_test)
            cv_scores[idx] = roc_auc_score(y_test, preds[:,1])
            cv_scores_train[idx] = roc_auc_score(y_train,model.predict_proba(X_train)[:,1]) - cv_scores[idx]
            
        return np.mean(cv_scores), np.mean(cv_scores_train)

class CherryPick:

    def __set_variables__(self, var, baseline):
        # Input data
        temp_var = var
        if baseline:
            temp_var = np.append(temp_var, 'random_variable')
            
        if isinstance(temp_var, list) or isinstance(temp_var, np.ndarray):
            temp_var = [x.replace(' ', '_') for x in temp_var]
        elif isinstance(temp_var, str):
            temp_var = temp_var.replace(' ', '_')
        else:
            raise TypeError('please, check the type of variable, the variable must be either str or list type')
        return temp_var
        

    def __init__(
                self,
                data,
                variables,
                target,
                study_cross_val = 5,
                num_studies = 50,
                overfit_thres = 0.01,
                log_lr_study=False,
                log_lgb_study=False,
                log_tree_study=False,
                verbosity = False,
                baseline = True
                ):

        self.variables = self.__set_variables__(var=variables, baseline=baseline)

        if isinstance(target, str):
            self.target = target.replace(' ', '_')
        else:
            raise TypeError('please, check the type of variable, the variable must be list type')
        
        self.data = data
        # inserindo a coluna com variável aleatória para comparação
        if not 'random_variable' in self.data.columns.tolist():
            self.data['random_variable'] = [np.random.random() for _ in self.data.index]


        self.study_cross_val = study_cross_val
        self.num_studies = num_studies
        self.overfit_thres = overfit_thres
        self.verbosity = verbosity

        self.log_lr_study=log_lr_study
        self.data_log_lr = None

        self.log_lgb_study=log_lgb_study
        self.data_log_lgb = None

        self.log_tree_study=log_tree_study
        self.data_log_tree = None

        # Output data
        self.data_most_important = pd.DataFrame()

        # Loading models
        self.lgbModel = None
        self.lrModel = None
        self.treeModel = None
        self.dummyModel = None

        # loading the objective function
        self.searchParams = SearchHyperParams(cross_val=self.study_cross_val)

        # redefining the features names in the data inserted
        self.data.columns = [x.replace(' ', '_') for x in self.data.columns.tolist()]


    # Defining feature importance functions
    def mutual_info(self, data: pd.DataFrame, explicable_vars: Union[str, list], target: str) -> list:
        """
        Function to calculate the mutual info between the explicable and target variables.

        Parameters:
        ----------
        data: pd.DataFrame
        Dataframe that will be used to choose the most important features
        
        """
        if isinstance(explicable_vars, str):
            df_ = data.dropna(subset=[explicable_vars, target], how='any', axis=0)
            df_ = df_[[explicable_vars, target]].copy()
        elif isinstance(explicable_vars, list):
            df_ = data.dropna(subset=explicable_vars + [target], how='any', axis=0)
            df_ = df_[explicable_vars + [target]].copy()
        df_ = df_.reset_index(drop=True)

        return mutual_info_classif(df_.drop(columns=[target]), df_[target], random_state=13)
    

    def logistic_roc(self, data: pd.DataFrame, explicable_vars: Union[str, list], target: str) -> float:
        """
        Função que obtém a roc de um modelo de regressão logística treinado 
        a partir de um conjunto de variáveis especificado.
        O modelo é otimizado via optuna.
        """
        
        if isinstance(explicable_vars, str):
            df_ = data.dropna(subset=target, how='any', axis=0)
            df_ = df_[[explicable_vars] + [target]].copy()

        elif isinstance(explicable_vars, list):
            df_ = data.dropna(subset=[target], how='any', axis=0)
            df_ = df_[explicable_vars + [target]].copy()
        else:
            raise ValueError("Variaveis deve ser uma instância list ou str")

        df_ = df_.reset_index(drop=True)

        try:
            study = optuna.create_study(directions=['maximize','minimize'])
            func = lambda trial: self.searchParams.objective_lr(trial, df_.drop(columns=target).fillna(0), df_[target])
            optuna.logging.set_verbosity(optuna.logging.WARNING)
            study.optimize(func, n_trials=self.num_studies)

            gdsOptuna = study.trials_dataframe()

            if self.log_lr_study:
                self.data_log_lr = gdsOptuna[(gdsOptuna['values_1'] < self.overfit_thres)].sort_values(['values_0','values_1'],ascending=[False, False])
            else:
                pass
                
            dicts = gdsOptuna[(gdsOptuna['values_1'] < self.overfit_thres)].sort_values(['values_0','values_1'],ascending=[False, False]).head(10).to_dict(orient='records')

                
            return dicts[0]['values_0']
        except Exception as e:
            print(e)
            return -1

    def run_tree(self,
                  dataframe,
                  colunas,
                  alvo
                  ):
  
        # Definindo um estudo optuna
        study = optuna.create_study(directions=['maximize','minimize'])
        func = lambda trial: self.searchParams.objective_decision_tree(trial, dataframe[colunas], dataframe[alvo])

        # Rodando o estudo optuna
        study.optimize(func, n_trials=self.num_studies)

        # Gerando os melhores hiperparâmetros para o modelo
        gdsOptuna = study.trials_dataframe()

        if self.log_tree_study:
            self.data_log_tree = gdsOptuna.sort_values(['values_0','values_1'], ascending=[False, False])
        else:
            pass

        dicts = gdsOptuna[(gdsOptuna['values_1'] < self.overfit_thres)].sort_values(['values_0','values_1'],ascending=[False, False]).head(10).to_dict(orient='records')
        params = {
            'criterion' : dicts[0]['params_criterion'],
            'splitter' : dicts[0]['params_splitter'],
            'min_samples_leaf' :dicts[0]['params_min_samples_leaf'],
            'min_samples_split' : dicts[0]['params_min_samples_split'],
            'max_leaf_nodes' : dicts[0]['params_max_leaf_nodes'],
            'ccp_alpha' : dicts[0]['params_ccp_alpha'],
            'max_depth' : dicts[0]['params_max_depth'],
            }

        # Treinando o modelo com os melhores hiperparâmetros
        self.treeModel = DecisionTreeClassifier(**params)
        self.treeModel.fit(
                            dataframe[colunas],
                            dataframe[alvo],
                            )
        return self.treeModel


    def _run_lgbm(self,
                  dataframe,
                  colunas,
                  alvo
                  ):
  
        # Definindo um estudo optuna
        study = optuna.create_study(directions=['maximize','minimize'])
        func = lambda trial: self.searchParams.objective_lgb(trial, dataframe[colunas], dataframe[alvo])

        # Rodando o estudo optuna
        study.optimize(func, n_trials=self.num_studies)

        # Gerando os melhores hiperparâmetros para o modelo
        gdsOptuna = study.trials_dataframe()

        if self.log_lgb_study:
            self.data_log_lgb = gdsOptuna.sort_values(['values_0','values_1'],ascending=[False, False])
        else:
            pass

        dicts = gdsOptuna[(gdsOptuna['values_1'] < self.overfit_thres)].sort_values(['values_0','values_1'],ascending=[False, False]).head(10).to_dict(orient='records')
        params = {
            'colsample_bytree' : dicts[0]['params_colsample_bytree'],
            'learning_rate' : dicts[0]['params_learning_rate'],
            'max_depth' :dicts[0]['params_max_depth'],
            'n_estimators' : dicts[0]['params_n_estimators'],
            'num_leaves' : dicts[0]['params_num_leaves'],
            'reg_alpha' : dicts[0]['params_lambda_l1'],
            'reg_lambda' : dicts[0]['params_lambda_l2'],
            }

        # Treinando o modelo com os melhores hiperparâmetros
        self.lgbModel = lgb.LGBMClassifier(objective="binary",**params)
        self.lgbModel.fit(
            dataframe[colunas], dataframe[alvo],
            eval_metric="auc",
            verbose=True
        )
        return self.lgbModel
    



    def gera_shap_score(self, dataframe: pd.DataFrame, colunas: Union[str, list], alvo: str)->list:
        if not self.verbosity:
            optuna.logging.set_verbosity(optuna.logging.WARNING)


        if not dataframe.equals(self.data):
            light_ = self._run_lgbm(dataframe, colunas, alvo, overfit_thres=self.overfit_thres)

            # Definindo os shap values
            explainer = shap.Explainer(light_, dataframe[colunas])
            shap_values = explainer(dataframe[colunas])

            
            # Gerando os dados
            arr_order = shap_values.abs.mean(0).argsort.flip.values

            # redefinindo o verbosity
            optuna.logging.set_verbosity(optuna.logging.DEBUG)

            return [pd.DataFrame(list(zip(np.array(shap_values.feature_names)[arr_order], np.array(shap_values.abs.mean(0).values)[arr_order])), columns=['variavel', 'shap_score']),
            shap_values]

        if not self.lgbModel:
        
            self._run_lgbm(dataframe, colunas, alvo)

        # Definindo os shap values
        explainer = shap.Explainer(self.lgbModel, dataframe[colunas])
        shap_values = explainer(dataframe[colunas])
        
        # Gerando os dados
        arr_order = shap_values.abs.mean(0).argsort.flip.values

        # redefinindo o verbosity
        optuna.logging.set_verbosity(optuna.logging.DEBUG)

        return [pd.DataFrame(list(zip(np.array(shap_values.feature_names)[arr_order], np.array(shap_values.abs.mean(0).values)[arr_order])), columns=['variavel', 'shap_score']),
        shap_values]


    def data_shap_score(self) -> pd.DataFrame:  
        metrica = 'shap_score_'+self.target
        # dic_ = {
        #     'variavel': [],
        #     metrica: []
        # }
        print(f'\n--- INICIALIZANDO A ESCORAGEM VIA SHAP SCORE PARA O ALVO {self.target}---\n ')
        aux = self.gera_shap_score(self.data, self.variables, self.target)[0]
        aux = aux.rename(columns={'shap_score': metrica})
        print(f'\n--- FINALIZADA A ESCORAGEM VIA SHAP SCORE PARA O ALVO {self.target}---\n ')
        return aux


    def data_lgbm_gain(self) -> pd.DataFrame:
        print(f'\n--- INICIALIZANDO A ESCORAGEM VIA LGBM GAIN PARA O ALVO {self.target}---\n ')
        if not self.lgbModel:
            self._run_lgbm(self.data, self.variables, self.target)
        metrica = 'lightGBM_gain_'+self.target

        print(f'\n--- FINALIZADA A ESCORAGEM VIA LGBM GAIN PARA O ALVO {self.target}---\n ')

        return pd.DataFrame(list(zip(
                                    #  [x.replace('_', ' ') for x in self.lgbModel.feature_name_],
                                     self.lgbModel.feature_name_,
                                     self.lgbModel.booster_.feature_importance(importance_type='gain'))),
                                     columns=['variavel', metrica]).sort_values(by=metrica, ascending=False)


    def data_lgbm_split(self) -> pd.DataFrame:
        print(f'\n--- INICIALIZANDO A ESCORAGEM VIA LGBM SPLIT PARA O ALVO {self.target}---\n ')
        if not self.lgbModel:
            self._run_lgbm(self.data, self.variables, self.target)
        metrica = 'lightGBM_split_'+self.target

        print(f'\n--- FINALIZADA A ESCORAGEM VIA LGBM SPLIT PARA O ALVO {self.target}---\n ')

        return pd.DataFrame(list(zip(
                                    #  [x.replace('_', ' ') for x in self.lgbModel.feature_name_],
                                     self.lgbModel.feature_name_,
                                     self.lgbModel.booster_.feature_importance(importance_type='split'))),
                                     columns=['variavel', metrica]).sort_values(by=metrica, ascending=False)


    def data_logistic_roc(self) -> pd.DataFrame:
        """
        Gera uma tabela ranqueando as variáveis com maior roc na regressão logística
        """

        print(f'\n--- INICIALIZANDO A ESCORAGEM VIA ROC LOGISTICA PARA O ALVO {self.target}---\n ')
        metrica = 'logistic_roc_'+ self.target
        dic_ = {
            'variavel': [],
            metrica: []
        }

        for variavel in tqdm(self.variables):
            dic_['variavel'].append(variavel)
            dic_[metrica].append(self.logistic_roc(self.data, variavel, self.target))

        print(f'\n--- FINALIZADA A ESCORAGEM VIA ROC LOGISTICA PARA O ALVO {self.target}---\n ')
        return pd.DataFrame(dic_).sort_values(by=metrica, ascending=False)


    def data_mutual_info(self) -> pd.DataFrame:
        """
        Gera uma tabela ranqueando as variáveis com maior informação mútua
        """

        print(f'\n--- INICIALIZANDO A ESCORAGEM VIA MUTUAL INFO PARA O ALVO {self.target}---\n ')

        metrica = 'mutual_info_' + self.target
        dic_ = {
            'variavel': [],
            metrica: []
        }

        for variavel in tqdm(self.variables):
            dic_['variavel'].append(variavel)
            dic_[metrica].append(self.mutual_info(self.data, variavel, self.target)[0])

        print(f'\n--- FINALIZADA A ESCORAGEM VIA MUTUAL INFO PARA O ALVO {self.target}---\n ')

        return pd.DataFrame(dic_).sort_values(by=metrica, ascending=False)


    def data_tree_gain(self) -> pd.DataFrame:
        print(f'\n--- INICIALIZANDO A ESCORAGEM VIA DECISION TREE GAIN PARA O ALVO {self.target}---\n ')
        if not self.treeModel:
            self.run_tree(self.data, self.variables, self.target)
        metrica = 'decisionTree_gain_'+self.target

        print(f'\n--- FINALIZADA A ESCORAGEM VIA DECISION TREE GAIN PARA O ALVO {self.target}---\n ')


        return pd.DataFrame(list(zip(self.treeModel.feature_names_in_,
                            self.treeModel.feature_importances_)),
                            columns=['variavel', metrica]).sort_values(by=metrica, ascending=False)


    def get_feature_importances(
                                self,
                                logistic_roc = True,
                                mutual_info = True,
                                shap_score = True,
                                tree_gain = True,
                                lgbm_gain = True,
                                lgbm_split = True,
                                cache: bool=True
                                ) -> pd.DataFrame:
        """
        Gera uma tabela compilando os resultados da roc logística, roc catboost,
        ganho de entropia catboost, e informação mútua
        """


        if cache and len(self.data_most_important):
           return self.data_most_important 
        

        else:
            temp_ = []

            if logistic_roc:
                try:
                    temp_.append(self.data_logistic_roc())
                except Exception as e:
                    print(e)
                    pass
            else:
                pass

            if mutual_info:
                try:
                    temp_.append(self.data_mutual_info())
                except Exception as e:
                    print(e)
                    pass
            else:
                pass

            if tree_gain:
                try:
                    temp_.append(self.data_tree_gain())
                except Exception as e:
                    print(e)
                    pass
            else:
                pass

            if shap_score:
                try:
                    temp_.append(self.data_shap_score())
                except Exception as e:
                    print(e)
                    pass
            else:
                pass

            if lgbm_gain:
                try:
                    temp_.append(self.data_lgbm_gain())
                except Exception as e:
                    print(e)
                    pass
            else:
                pass

            if lgbm_split:
                try:
                    temp_.append(self.data_lgbm_split())
                except Exception as e:
                    print(e)
                    pass
            else:
                pass

            try:
                self.data_most_important = reduce(lambda right, left: pd.merge(right, left, on='variavel'), temp_)
            except:
                print('Alguma coisa deu errado!')
            return self.data_most_important



    def __standard_score__(self, df, metrics_column):
        df_ = df.sort_values(by=metrics_column[0], ascending=False)
        df_['standard_score'] = [x for x in range(len(df)-1, -1, -1)]
        
        for metric in metrics_column[1:]:
            df_ = df_.sort_values(by=metric, ascending=False)
            df_['temp_score'] = [x for x in range(len(df)-1, -1, -1)]

            df_['standard_score'] = df_[['standard_score', 'temp_score']].sum(axis=1)

            df_ = df_.drop(columns='temp_score')

        return df_.sort_values(by='standard_score', ascending=False)
    
    def __cluster_score__(
                            self,
                            df,
                            metrics_column,
                            n_cluster=8,
                            init='k-means++',
                            n_init=10,
                            tol=1e-4,
                            verbose=0,
                            random_state=13,
                            algorithm='lloyd'
                            ):
        df_ = df.sort_values(by=metrics_column[0], ascending=False)

        df_scaled = df_.copy()

        for col in metrics_column[1:]:
            scaler = MinMaxScaler()

            df_scaled[col] = scaler.fit_transform(df_[[col]])

        cluster = KMeans(n_clusters=n_cluster,
                        init=init,
                        n_init=n_init,
                        tol=tol,
                        verbose=verbose,
                        random_state=random_state,
                        algorithm=algorithm
                        )
        cluster.fit(df_scaled[metrics_column[1:]])

        df_['clusters'] = cluster.predict(df_scaled[metrics_column[1:]])
        df_['cluster_score'] = df_scaled[metrics_column[1:]].mean(axis=1)
        
        return df_.sort_values(by='cluster_score', ascending=False)



        
    def calculate_score(self, df: pd.DataFrame, metrics_column: list, strategy='standard'):
        """
        Dado o dataframe, e as colunas com as métricas. Calcula o score por ranqueamento das métricas.
        A primeira coluna do dataframe deve ser a coluna de variáveis. Todas as demais devem ser numéricas.
        """

        if strategy == 'standard':

            return self.__standard_score__(df=df, metrics_column=metrics_column)
        
        elif strategy == 'cluster_score':
            return self.__cluster_score__(df=df, metrics_column=metrics_column)
        



def limiar_score(predictions: Union[list, np.ndarray], target: Union[list, np.ndarray]) -> dict:
    """
    Dada uma entrada de previsão probabilística, e uma lista com a variável alvo real,
    obtém o limiar ótimo de classificação.

    Parâmetros:
    ----------
    predictions: Union[list, np.ndarray]
    Iterável com probabilidades de previsão da variável alvo.

    target: Union[list, np.ndarray]
    Iterável com as informações reais da variável alvo.

    Retorna:
    -------
    limiar_score: dict
    Dicionário com informação do limiar ótimo e de algumas de suas métricas de classificação
    como precisão, recall, acurácia, roc-auc e f1-score.

    Developed by: Vinícius Ormenesse - https://github.com/ormenesse
    """
    #Imprimindo limiar de Escore
    fpr, tpr, threshold = roc_curve(target, predictions)
    i = np.arange(len(tpr)) 
    roc = pd.DataFrame({'tf' : pd.Series(tpr-(1-fpr), index=i), 'threshold' : pd.Series(threshold, index=i)})
    roc_t = roc.loc[(roc.tf-0).abs().argsort()[:1]]
    # print('Limiar que maxima especificidade e sensitividade:')
    # print(list(roc_t['threshold']))
    #analisando modelo com novo limiar
    tn, fp, fn, tp = confusion_matrix(target, [1 if item>=list(roc_t['threshold'])[0] else 0 for item in predictions]).ravel()
    Precision = tp/(tp+fp)
    Recall = tp/(tp+fn)
    acuracia = (tp+tn)/(tn+fp+fn+tp)
    F = (2*Precision*Recall)/(Precision+Recall)
    return {'precision': Precision,
            'recall': Recall,
            'acuracia': acuracia,
            'f-score': F,
            'roc-auc': roc_auc_score(target, predictions),
            'threshold': float(roc_t['threshold'])
            }

def __get_features_threshold_score__(df: pd.DataFrame, variables: Union[list, np.ndarray], target: str) -> pd.DataFrame:
    """
    Obtém o limiar ótimo de classificação de cada variável especificada.

    Parâmetros:
    ----------
    df: pd.DataFrame
    base de dados que contém os dados referentes à variável explicativa e a variável alvo.

    variables: Union[list, np.ndarray]
    lista com o nome das variáveis explicativas que se deseja obter o limiar de classificação ótimo.

    target: Union[list, np.ndarray]
    nome da variável alvo

    Retorna:
    -------
    __get_features_threshold_score__: pd.DataFrame
    Dataframe contendo para cada variável explicativa o seu limiar normalizada e não-normalizado.
    O limiar especifica a partir de qual valor, podemos delimitar as classes da variável alvo de 
    maneira a otimizar a especificidade e sensitividade.


    
    """
    temp = df[[target]]

    array_thres = []
    for variable in variables:
        scale = MinMaxScaler()
        temp[variable] = scale.fit_transform(df[[variable]])
        temp[variable] = temp[variable].fillna(-1)

        limiar_temp = limiar_score(temp[variable], temp[target])
        limiar_temp.update({'variable': variable})
        limiar_temp.update({'threshold_variable': scale.inverse_transform([[limiar_temp['threshold']]])[0][0]})

        array_thres.append(pd.DataFrame(limiar_temp, index=[0]))

    return pd.concat(array_thres, axis=0)

def __best_threshold_classification__(df: pd.DataFrame, variables: Union[list, np.ndarray], target: str) -> pd.DataFrame:
    """
    Realiza uma previsão da variável alvo a partir de cada uma de suas variáveis explicativas,
    a classificação é realizada de maneira separada entre as variáveis explicativas, utilizando
    apenas os seus respectivos valores de limiar ótimo. A ordem de classificação a partir do 
    limiar é definida de acordo com a ordem que oferece a classificação de maior roc.

    Parâmetros:
    ----------
    df: pd.DataFrame
    base de dados que contém os dados referentes à variável explicativa e a variável alvo.

    variables: Union[list, np.ndarray]
    lista com o nome das variáveis explicativas

    Retorna:
    -------
    __best_threshold_classification__: pd.DataFrame
    Um dataframe cuja cada coluna apresenta a classificação do mesmo a partir do seu limiar
    ótimo.

    target: Union[list, np.ndarray]
    nome da variável alvo

    """
    temp_ = __get_features_threshold_score__(df, variables, target)

    df_temp = df.copy()

    for variable in variables:
        temp_thres = temp_[temp_['variable']==variable]['threshold_variable'][0]
        # print(temp_thres, type(temp_thres))

        # Verificando como o limiar deve ser aplicado de maneira a maximizar a roc-auc
        ## 1 se x>=temp_thres
        temp_list_geq_thres = df_temp[variable].apply(lambda x: 1 if x>=temp_thres else 0)

        score_geq_thres = roc_auc_score(df_temp[target], temp_list_geq_thres)

        ## 1 se x<=temp_thres
        temp_list_leq_thres = df_temp[variable].apply(lambda x: 1 if x<=temp_thres else 0)

        score_leq_thres = roc_auc_score(df_temp[target], temp_list_leq_thres)

        if score_geq_thres>=score_leq_thres:
            df_temp[variable] = temp_list_geq_thres

        else:
            df_temp[variable] = temp_list_leq_thres

    return df_temp



def __set_difficulty_group__(df: pd.DataFrame, target: str) -> pd.DataFrame:
    """
    Define os grupos de dificuldade de classificação das linhas a partir da taxa
    de acerto das variáveis explicativas.
    As linhas cuja taxa de acerto supere a média, serão postas na classe de linhas
    fáceis de serem classificadas. Por outro lado, linhas com taxa de acerto inferior
    à média, serão rediracionadas ao grupo das linhas mais difíceis de serem 
    classificadas.

    """
    sucess_list = []
    for ind in df.index:
        rate_0 = df.drop(columns=target).T[ind].value_counts()[0]/df.drop(columns=target).T.shape[0]
        rate_1 = df.drop(columns=target).T[ind].value_counts()[1]/df.drop(columns=target).T.shape[0]

        if df[target].iloc[ind]==0:
            sucess_list.append(rate_0)

        elif df[target].iloc[ind]==1:
            sucess_list.append(rate_1)

        else:
            raise Exception('data target must be binary class.')

    df['sucess_rate'] = sucess_list

    difficulty_threshold = df['sucess_rate'].mean()

    # We set the group 1 as the group with the more difficult lines to classifier
    # as follows, the group 0 regards to the group with easiest lines
    df['difficulty_group'] = df['sucess_rate'].apply(lambda x: 0 if x >= difficulty_threshold else 1)
    

    return df


def __generate_stats_sucess__(
                             df: pd.DataFrame,
                             variables: Union[list, np.ndarray],
                             target: str,
                             g0_weight=[0.1, 0.3, 1.0],
                             g1_weight=[0.25, 0.5, 1.0]
                             ) -> pd.DataFrame:
    
    """
    Gera o cherry score juntamente com as estatísticas utilizadas para o cálculo do mesmo.
    Dentre as estatísticas estão a faixa da taxa de acerto de cada variável entre os grupos
    de maior e menor dificuldade de classificação, quartil da variável em relação aos grupos,
    e o cherry score.

    Parâmetros:
    ----------
    df: pd.DataFrame
    base de dados com as variáveis que se deseja obter o cherry score

    variables: Union[list, np.ndarray]
    iterável com as variáveis que se deseja calcular o cherry score

    target:
    variável alvo

    g0_weight: list
    Peso dado de acordo com a taxa de acerto de uma variável no grupo das linhas mais fáceis.
    O peso é associado ao quartil que a variável assume no grupo. Quanto menor o quartil, menos
    acertos a variável teve no grupo, portanto, menor será o peso.

    g1_weight: list
    Peso dado de acordo com a taxa de acerto de uma variável no grupo das linhas mais difíceis.
    O peso é associado ao quartil que a variável assume no grupo. Quanto menor o quartil, menos
    acertos a variável teve no grupo, portanto, menor será o peso.

    Retorna:
    __generate_stats_sucess__: pd.DataFrame
    Dataframe com cherry score, juntamente com as métricas estatísticas utilizadas para o seu cálculo.
    -------


    """
    df_ = pd.DataFrame({'variable': [], 'sucess_rate_g0': [], 'sucess_rate_g1': []})



    for var in variables:    
    
        check_list = pd.DataFrame({'rightClassification': [], 'difficulty_group': []})
        for ind in df.index:

            if df[target].iloc[ind]==df[var].iloc[ind]:
                check_list.loc[len(check_list)] = {'rightClassification': 1, 'difficulty_group': df.iloc[ind]['difficulty_group']}
            elif df[target].iloc[ind]==1:
                check_list.loc[len(check_list)] = {'rightClassification': 0, 'difficulty_group': df.iloc[ind]['difficulty_group']}

            else:
                check_list.loc[len(check_list)] = {'rightClassification': np.nan, 'difficulty_group': df.iloc[ind]['difficulty_group']}

        sucess_rate_g0 = check_list.loc[check_list['difficulty_group']==0, 'rightClassification'].sort_values().value_counts()[1]/check_list[check_list['difficulty_group']==0].shape[0]
        sucess_rate_g1 = check_list.loc[check_list['difficulty_group']==1, 'rightClassification'].sort_values().value_counts()[1]/check_list[check_list['difficulty_group']==1].shape[0]

        df_.loc[len(df_)] = {'variable': var, 'sucess_rate_g0': sucess_rate_g0, 'sucess_rate_g1': sucess_rate_g1}



    df_['g0_quantile'] = df_['sucess_rate_g0'].apply(
                                                    lambda x:
                                                    'Q1' if x<=df_['sucess_rate_g0'].quantile(0.33)
                                                    else
                                                    (
                                                    'Q2' if x<=df_['sucess_rate_g0'].quantile(0.66)
                                                    else 'Q3'
                                                    )
                                                )

    df_['g1_quantile'] = df_['sucess_rate_g1'].apply(
                                                    lambda x:
                                                    'Q1' if x<=df_['sucess_rate_g1'].quantile(0.33)
                                                    else (
                                                    'Q2' if x<=df_['sucess_rate_g1'].quantile(0.66)
                                                    else 'Q3'
                                                    )
                                                )

    df_['g0_quantile_score'] = df_['g0_quantile'].apply(
                                                        lambda x:
                                                        g0_weight[2] if x=='Q3'
                                                        else (
                                                        g0_weight[1] if x=='Q2'
                                                        else g0_weight[0]
                                                        )
                                                    )

    df_['g1_quantile_score'] = df_['g1_quantile'].apply(
                                                        lambda x:
                                                        g1_weight[2] if x=='Q3'
                                                        else (
                                                        g1_weight[1] if x=='Q2'
                                                        else g1_weight[0]
                                                        )
                                                        )

    df_ = df_.assign(cherry_score = lambda x: (x['g0_quantile_score']*x['sucess_rate_g0']+x['g1_quantile_score']*x['sucess_rate_g1'])/2)


    return df_.sort_values(by='cherry_score', ascending=False)


def generate_cherry_score(df, variables, target, only_score=True):
    """
    Função que organiza o pipeline necessário para o cálculo do cherry score.
    
    """
    classfied_df = __best_threshold_classification__(df=df, variables=variables, target=target)

    # creating a column with difficulty group
    df_difficulty = __set_difficulty_group__(df=classfied_df, target=target)

    df_score = __generate_stats_sucess__(df=df_difficulty, variables=variables, target=target)

    if only_score:
        return df_score[['variable', 'cherry_score']]
    else:
        return df_score
      


# df_





    


if __name__ == '__main__':
    pass