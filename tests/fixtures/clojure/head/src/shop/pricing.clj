(ns shop.pricing
  (:require [clojure.string :as str]))

(def rate 2)

(defmulti discount :tier)

(defmethod discount :gold [order]
  (quot (:amount order) 5))

(defmethod discount :default [order]
  (quot (:amount order) 10))

(defn amount->cents [amount]
  (* amount 100))

(defn base-price [amount]
  (let [local-total (* amount rate)]
    (- local-total (discount {:tier :default :amount amount}))))

(defn describe [amount]
  (str/join " " ["price" (amount->cents (base-price amount))]))
